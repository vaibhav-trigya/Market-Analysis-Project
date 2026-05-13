import sys
import os

# Ensure bundled dependencies in temp_libs are accessible
temp_libs_path = os.path.join(os.path.dirname(__file__), "temp_libs")
if os.path.exists(temp_libs_path) and temp_libs_path not in sys.path:
    sys.path.insert(0, temp_libs_path)

import re
import hashlib
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright # pyrefly: ignore [missing-import] # type: ignore

# Constants
BASE_URL = "https://www.zoho.com"
PARTNER_LIST_URL = "https://www.zoho.com/partners/find-zoho-partner.html"
PARTNER_SEARCH_URL = "https://www.zoho.com/partners/find-zoho-partner.html"

def merge_and_dedup(target: dict, source: dict):
    """Merges source collections into target collections and removes duplicate links."""
    for key in ["blogs", "case_studies", "customer_stories"]:
        if key in source and isinstance(source[key], list):
            if key not in target:
                target[key] = []
            
            existing_links = {str(item.get("link", "")).rstrip("/") for item in target[key]}
            for item in source[key]:
                link = str(item.get("link", "")).rstrip("/")
                if link and link not in existing_links:
                    target[key].append(item)
                    existing_links.add(link)

# Import modularized functions
from extractors import (
    extract_name, extract_overview, extract_website, extract_linkedin,
    extract_customer_stories, extract_blogs, extract_case_studies,
    extract_from_external_website, extract_page_content, extract_from_manual_links,
    _collect_all_nav_links, _expand_nav_fully, extract_linkedin_from_external,
    extract_social_links, scrape_social_platform,
    is_ecommerce_site, has_content_signals_in_nav,
    check_content_threshold, run_fallback_data_collection,
    extract_homepage_services, universal_site_crawler,
    extract_all_page_content
)
from analyzer import PartnerAnalyzer

class MarketIntelligenceAgent:
    def __init__(self, partner_name: str | None = None, headless: bool = True, analyzer: PartnerAnalyzer | None = None, parent_company: str | None = None):
        self.partner_name = partner_name
        self.headless = headless
        self.analyzer = analyzer or PartnerAnalyzer()
        self.parent_company = parent_company
        self.browser = None
        self.page = None

    def _launch(self, playwright):
        self.browser = playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-infobars',
                '--disable-extensions',
                '--no-first-run',
                '--ignore-certificate-errors',
                '--disable-background-networking',
                '--disable-default-apps',
                '--disable-sync',
                '--metrics-recording-only',
                '--mute-audio',
                '--window-size=1920,1080'
            ]
        )
        context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
            java_script_enabled=True,
            device_scale_factor=1,
            has_touch=False,
            is_mobile=False,
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0"
            }
        )
        self.page = context.new_page()
        # Global timeouts — prevents infinite hangs on server
        self.page.set_default_timeout(30000)
        self.page.set_default_navigation_timeout(40000)
        # Hide automation flags from websites
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)

    def _safe_goto(self, url: str, timeout: int = 40000, wait_until: str = "domcontentloaded"):
        """Attempt to navigate with retry logic and browser context recovery."""
        import time
        import random

        for attempt in range(3): # Increased to 3 attempts
            try:
                time.sleep(random.uniform(1.0, 2.0))
                return self.page.goto(url, wait_until=wait_until, timeout=60000)
            except Exception as e:
                err_msg = str(e).lower()
                
                # SPECIAL HANDLING FOR ERR_ABORTED (Firewall/Bot Block)
                # If we get aborted on a deep link, we try the "Homepage Handshake"
                if "net::err_aborted" in err_msg and attempt < 2:
                    try:
                        parsed = urlparse(url)
                        base_domain = f"{parsed.scheme}://{parsed.netloc}/"
                        print(f"[*] Connection aborted for deep link. Attempting 'Human Handshake' via root: {base_domain}", file=sys.stderr)
                        
                        # 1. Visit root first to establish cookies/session
                        self.page.goto(base_domain, wait_until="commit", timeout=20000)
                        
                        # Mimic human activity: scroll slightly then wait
                        self.page.mouse.wheel(0, 500)
                        time.sleep(random.uniform(1.0, 2.0)) 
                        self.page.mouse.wheel(0, -200)
                        
                        print(f"[*] Handshake complete. Proceeding to retry {url}...", file=sys.stderr)
                        # No return here - let the loop continue to the next attempt which will hit the deep link
                    except Exception as he:
                        print(f"[*] Handshake failed: {he}", file=sys.stderr)
                        pass 

                if "net::err_aborted" not in err_msg:
                    print(f"[*] Attempt {attempt+1} failed for {url}: {e}", file=sys.stderr)

                is_protocol_err = "protocol_error" in err_msg or "http2" in err_msg
                
                # Detect dead browser context
                is_dead_context = "context or browser has been closed" in err_msg or "target page" in err_msg

                if is_protocol_err or is_dead_context:
                    print(f"[!] Critical error detected ({'Protocol' if is_protocol_err else 'Dead Context'}). Attempting context recovery...", file=sys.stderr)
                    try:
                        # Create a fresh context WITHOUT the problematic extra_http_headers if it's a protocol error
                        context_args = {
                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/124.0.0.0",
                            "viewport": {"width": 1920, "height": 1080},
                            "ignore_https_errors": True,
                        }
                        
                        # Only include standard headers for protocol error retries to avoid HTTP/2 mismatches
                        if not is_protocol_err:
                            context_args["extra_http_headers"] = {
                                "Accept-Language": "en-US,en;q=0.9",
                                "Upgrade-Insecure-Requests": "1"
                            }

                        context = self.browser.new_context(**context_args)
                        self.page = context.new_page()
                        self.page.set_default_timeout(30000)
                        self.page.set_default_navigation_timeout(40000)
                        
                        # Use a more lenient wait state for the recovery attempt
                        print(f"[+] Context recovered. Retrying {url} with lenient wait...", file=sys.stderr)
                        return self.page.goto(url, wait_until="commit", timeout=40000)
                    except Exception as recovery_err:
                        print(f"[-] Context recovery failed: {recovery_err}", file=sys.stderr)
                        if attempt == 2: return None
                        continue

                if attempt == 0:
                    print(f"[*] Retrying {url} with lenient 'commit' wait...", file=sys.stderr)
                    wait_until = "commit"
                elif attempt == 1:
                    print(f"[*] Retrying {url} with extended timeout...", file=sys.stderr)
                    wait_until = "commit"
                else:
                    return None
        return None

    def _close(self):
        if self.browser:
            self.browser.close()

    def _safe_text(self, selector: str, root=None) -> str | None:
        ctx = root if root else self.page
        try:
            el = ctx.query_selector(selector)
            return el.inner_text().strip() if el else None
        except Exception:
            return None

    def _safe_attr(self, selector: str, attr: str, root=None) -> str | None:
        ctx = root if root else self.page
        try:
            el = ctx.query_selector(selector)
            return el.get_attribute(attr) if el else None
        except Exception:
            return None

    def _absolute_url(self, href: str | None) -> str | None:
        if not href: return None
        href = href.strip()
        if href.startswith("http"): return href
        if href.startswith("//"): return "https:" + href
        base = self.page.url if self.page else BASE_URL
        return urljoin(base, href)

    def _scroll_to_bottom(self):
        # 1. Quick mid-page and bottom-page trigger for lazy loaders (WordPress/Elementor style)
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            self.page.wait_for_timeout(1000)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(1000)
        except: pass

        # 2. Detailed incremental scroll to ensure everything is rendered
        self.page.evaluate("""
            async () => {
                await new Promise(resolve => {
                    let total = 0;
                    const step = 400;
                    const timer = setInterval(() => {
                        window.scrollBy(0, step);
                        total += step;
                        if (total >= document.body.scrollHeight) {
                            clearInterval(timer);
                            resolve();
                        }
                    }, 150);
                });
            }
        """)
        self.page.wait_for_timeout(1500)

    def _try_switch_to_english(self):
        """Attempts to find and click an English language switcher on the page."""
        print("[*] Checking for English language switcher...", file=sys.stderr)

        en_selectors = [
            "a:has-text('English')",
            "a:has-text('EN')",
            "button:has-text('English')",
            "a[aria-label*='English' i]",
            "a[title*='English' i]",
            "a[href*='/en/']",
            "a[href*='lang=en']"
        ]

        for selector in en_selectors:
            try:
                el = self.page.locator(selector).first
                if el.count() > 0 and el.is_visible():
                    print(f"[+] Found language switcher: {selector}. Switching to English...", file=sys.stderr)
                    el.click()
                    # Wait for navigation to finish AND network to settle
                    self.page.wait_for_load_state("networkidle", timeout=15000)
                    self.page.wait_for_timeout(3000) # Safety buffer for JS rendering
                    return True
            except Exception:
                continue

        return False

    def apply_filters(self):
        print("[*] Navigating to partner list and applying experience filters...", file=sys.stderr)
        self._safe_goto(PARTNER_LIST_URL, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(5000)

        india_filter_remove = self.page.locator("xpath=//span[text()='Country: India']/following-sibling::span[contains(@class, 'close') or contains(@class, 'remove')]")
        if india_filter_remove.count() > 0:
            india_filter_remove.first.click()
            self.page.wait_for_timeout(2000)

        experience_header = self.page.locator("xpath=//span[text()='Experience']/parent::div")
        try:
            experience_header.wait_for(state="visible", timeout=10000)
            experience_header.click()
            self.page.wait_for_timeout(1000)
        except Exception: pass

        for kw in ['7 - 9 years', 'More than 9 years']:
            try:
                cb = self.page.locator(f"xpath=//label[contains(., '{kw}')]")
                cb.wait_for(state="visible", timeout=5000)
                cb.click()
                self.page.wait_for_timeout(2000)
            except Exception: pass

        self.page.wait_for_timeout(3000)

    def get_all_partners(self) -> list[dict]:
        print("[*] Extracting partner list...", file=sys.stderr)
        self._scroll_to_bottom()
        partners = []
        cards = self.page.locator("li.partner-card, li:has(strong)").all()
        for card in cards:
            try:
                name_el = card.locator("strong, .partner-name, h3").first
                if name_el.count() == 0: continue
                name = name_el.inner_text().strip()
                link_el = card.locator("a[href*='partner']").first
                href = link_el.get_attribute("href") if link_el.count() > 0 else None
                if name and href:
                    abs_url = self._absolute_url(href)
                    if "find-partner-profile.html" in abs_url or "partnerid=" in abs_url:
                        partners.append({"name": name, "url": abs_url})
            except Exception: continue
        return partners

    def find_partner(self) -> str:
        if self.partner_name.startswith("http"):
            return self.partner_name

        if re.match(r"^[a-fA-F0-9]{30,}$", self.partner_name):
            return f"https://www.zoho.com/partners/find-partner-profile.html?partnerid={self.partner_name}"

        print(f"[*] Searching for partner: {self.partner_name!r}", file=sys.stderr)
        self._safe_goto(PARTNER_SEARCH_URL, timeout=45000)
        self.page.wait_for_timeout(3000)

        search_selectors = ["#search-partner", "input#search-partner", "input[placeholder*='search' i]"]
        search_input = None
        for sel in search_selectors:
            el = self.page.query_selector(sel)
            if el and el.is_visible():
                search_input = el
                break

        if search_input:
            search_input.fill(self.partner_name)
            search_input.press("Enter")
            self.page.wait_for_timeout(3000)

        self._scroll_to_bottom()
        partner_url = self._find_matching_card()
        if partner_url: return partner_url
        raise RuntimeError(f"Partner '{self.partner_name}' not found.")

    def _find_matching_card(self) -> str | None:
        target = self.partner_name.lower().strip()
        profile_link_patterns = ["a[href*='find-partner-profile.html']", "a[href*='partnerid=']"]
        for sel in profile_link_patterns:
            anchors = self.page.query_selector_all(sel)
            for anchor in anchors:
                try:
                    text = anchor.inner_text().strip().lower()
                    href = anchor.get_attribute("href") or ""
                    if target in text or text in target:
                        abs_url = self._absolute_url(href)
                        if "find-partner-profile.html" in abs_url: return abs_url
                except Exception: continue
        return None

    def extract_partner_data(self, profile_url: str, manual_links: dict | None = None) -> dict:
        print(f"[*] Opening profile: {profile_url}", file=sys.stderr)
        try:
            success = self._safe_goto(profile_url, timeout=45000)
            if not success:
                print(f"[-] Warning: Initial page load for {profile_url} failed.", file=sys.stderr)
            self.page.wait_for_timeout(3000)
            self._scroll_to_bottom()
        except Exception as e:
            print(f"[-] Warning: Error during initial page load for {profile_url}: {e}", file=sys.stderr)

        is_zoho_profile = "zoho.com" in profile_url and ("find-partner-profile.html" in profile_url or "partnerid=" in profile_url)

        if is_zoho_profile:
            from urllib.parse import parse_qs
            parsed_url = urlparse(profile_url)
            params = parse_qs(parsed_url.query)
            partner_id = params.get('partnerid', ['unknown'])[0]

            data = {
                "partner_id": partner_id,
                "name": extract_name(self),
                "overview": extract_overview(self),
                "website": extract_website(self),
                "linkedin": extract_linkedin(self),
                "customer_stories": extract_customer_stories(self),
                "blogs": [],
                "case_studies": [],
                "general_content": [],
                "social_media": {"instagram": None, "twitter": None, "facebook": None, "youtube": None},
                "parent_company": self.parent_company
            }
            print(f"[*] Extracting core identity for {data['name']}...", file=sys.stderr)

            if not data["website"]:
                data["blogs"] = extract_blogs(self)
                data["case_studies"] = extract_case_studies(self)
                data["general_content"] = []

            if data["customer_stories"]:
                print(f"[*] Extracting content for {len(data['customer_stories'])} stories found on Zoho profile...", file=sys.stderr)
                for item in data["customer_stories"][:5]:
                    if item.get("link") and (not item.get("content") or "failed" in item.get("content", "").lower()):
                        item["content"] = extract_page_content(self, item["link"])
        else:
            print(f"[*] Treating {profile_url} as external website...", file=sys.stderr)
            url_hash = hashlib.md5(profile_url.encode()).hexdigest()[:12]

            page_title = ""
            try:
                page_title = self.page.title()
            except: pass

            extracted_name = extract_name(self)

            if extracted_name == "Blocked Content":
                print(f"[-] Scrape blocked for {profile_url} — returning partial data, fallback will run.", file=sys.stderr)
                data = {
                    "partner_id": f"ext_{url_hash}",
                    "name": self.analyzer.extract_company_name_with_ai(profile_url),
                    "overview": "Scrape blocked — bot protection detected.",
                    "website": profile_url,
                    "linkedin": None,
                    "customer_stories": [],
                    "blogs": [],
                    "case_studies": [],
                    "general_content": [],
                    "social_media": {"instagram": None, "twitter": None, "facebook": None, "youtube": None},
                    "parent_company": self.parent_company,
                    "fallback_scores": None,
                    "fallback_data": None,
                    "scrape_status": "blocked"
                }
                # Immediately trigger fallback for blocked sites
                from extractors import run_fallback_data_collection
                fallback_result = run_fallback_data_collection(
                    company_name=data["name"],
                    website_url=profile_url,
                    linkedin_url=""
                )
                data["fallback_scores"] = self.analyzer.score_from_fallback_data(data["name"], fallback_result)
                data["fallback_data"]   = fallback_result
                return data

            lower_name = extracted_name.lower()
            if len(extracted_name) > 35 or \
               any(word in lower_name for word in ["way to", "welcome", "home", "the easiest", "zoho consultant", "zoho partner"]):
                print(f"[*] Extracted name '{extracted_name}' looks generic. Using AI to find actual brand name...", file=sys.stderr)
                name = self.analyzer.extract_company_name_with_ai(profile_url)
            else:
                name = extracted_name

            data = {
                "partner_id": f"ext_{url_hash}",
                "name": name,
                "overview": extract_overview(self) or "No overview found on external site.",
                "website": profile_url,
                "linkedin": None,
                "customer_stories": [],
                "blogs": [],
                "case_studies": [],
                "general_content": [],
                "social_media": {
                    "overall_summary": "Analysis active.",
                    "key_positioning": [],
                    "observations": [],
                    "platforms": {"instagram": None, "twitter": None, "facebook": None, "youtube": None}
                },
                "parent_company": self.parent_company
            }

        if data["website"]:
            if "Scrape Failed" in (data.get("overview") or ""):
                print(f"[!] Stopping deep scrape: Main website {data['website']} is blocked.", file=sys.stderr)
                return data

            print(f"[*] Official Website: {data['website']}", file=sys.stderr)
            print(f"[*] Starting Deep Content Extraction for {data['name']}...", file=sys.stderr)

            print(f"[*] AI is discovering Blog and Case Study links for {data['website']}...", file=sys.stderr)
            ai_blog_url, ai_case_url, ai_story_url = None, None, None
            try:
                # FIX: Reduced timeout for external sites — 20s is enough for most sites
                # Saves 25s per company on slow/JS-heavy sites like boAt, Nykaa, Meesho
                self._safe_goto(data["website"], timeout=20000)
                self.page.wait_for_timeout(1500)

                self._try_switch_to_english()

                if not data["linkedin"]:
                    data["linkedin"] = extract_linkedin_from_external(self, data["website"])
                    if data["linkedin"]:
                        print(f"[+] Discovered LinkedIn from website: {data['linkedin']}")

                domain = urlparse(data["website"]).netloc.replace("www.", "")

                # FIX: Check if site is e-commerce BEFORE expanding nav or deep scraping
                # E-commerce sites (boAt, Nykaa, Meesho) never have blogs/case studies
                # Skipping them saves 2-4 minutes per site
                from extractors import is_ecommerce_site, has_content_signals_in_nav
                if is_ecommerce_site(self.page):
                    print(f"[!] E-commerce site detected for {data['name']} — skipping deep scrape, triggering fallback directly.", file=sys.stderr)
                    # Still collect social links (fast operation)
                    social_links = extract_social_links(self)
                    for platform, url in social_links.items():
                        if url:
                            data["social_media"][platform] = scrape_social_platform(self, url, platform)
                    # Jump straight to fallback — no nav expansion, no deep scrape
                    from extractors import run_fallback_data_collection
                    _fb = run_fallback_data_collection(
                        company_name=data.get("name", ""),
                        website_url=data.get("website", ""),
                        linkedin_url=data.get("linkedin", "")
                    )
                    data["fallback_scores"] = self.analyzer.score_from_fallback_data(data["name"], _fb)
                    data["fallback_data"]   = _fb
                    return data

                # FIX: Collect nav links FIRST, check for content signals
                # before running the expensive _expand_nav_fully
                nav_links = _collect_all_nav_links(self.page, domain)

                if has_content_signals_in_nav(nav_links):
                    # Content signals found in nav — worth expanding and deep scraping
                    print(f"[*] Content signals found in nav — running full nav expansion.", file=sys.stderr)
                    _expand_nav_fully(self.page)
                    nav_links = _collect_all_nav_links(self.page, domain)
                else:
                    # No content signals — site might be small or dynamic.
                    # We run a partial expansion anyway to be safe.
                    print(f"[*] No obvious content signals in nav for {data['name']} — running safety expansion.", file=sys.stderr)
                    _expand_nav_fully(self.page)
                    # Re-collect links after expansion
                    nav_links = _collect_all_nav_links(self.page, domain)

                print(f"[*] Discovering Social Media links from {data['website']}...", file=sys.stderr)
                social_links = extract_social_links(self)

                # Only call AI discovery if the page found nothing at all (saves API + time)
                found_any = any(v for v in social_links.values())
                if not found_any:
                    ai_social = self.analyzer.find_social_links_with_ai(data["name"], data["website"])
                    for platform, url in ai_social.items():
                        if platform == "linkedin":
                            if not data["linkedin"] and url:
                                data["linkedin"] = url
                                print(f"[+] AI Discovered LinkedIn: {url}")
                        elif not social_links.get(platform) and url:
                            print(f"[+] AI Discovered {platform}: {url}")
                            social_links[platform] = url
                # --- PHASE 1: BROWSER-BASED DISCOVERY & SCRAPING ---
                # Attempt to find and scrape platforms directly (fastest, but often blocked)
                for platform, url in social_links.items():
                    if url and not data["social_media"]["platforms"].get(platform):
                        data["social_media"]["platforms"][platform] = scrape_social_platform(self, url, platform)

                # --- PHASE 2: AI DEEP INTELLIGENCE (THE MASTER) ---
                # We trigger AI discovery to FILL GAPS and OVERWRITE poor quality data.
                has_content = any(
                    isinstance(info, dict) and (info.get("bio") or info.get("brand_voice"))
                    for info in data["social_media"]["platforms"].values()
                    if info
                )
                
                if not all(social_links.values()) or not has_content:
                    print(f"[*] Launching AI Strategic Discovery for {data['name']} to fetch brand intelligence...")
                    ai_social = self.analyzer.find_social_links_with_ai(data["name"], data["website"])
                    
                    if ai_social and ai_social.get("platforms"):
                        # MASTER OVERWRITE: Use high-quality AI data for everything
                        data["social_media"] = ai_social
                        
                        # Sync LinkedIn back to top-level
                        li_info = ai_social["platforms"].get("linkedin")
                        if li_info and li_info.get("url"):
                            data["linkedin"] = li_info["url"]
                            print(f"[+] AI Discovered LinkedIn: {li_info['url']}")
                        
                        print(f"[+] AI Social Intelligence successfully synced for {data['name']}.")

                # --- HYBRID DISCOVERY STRATEGY ---
                # 1. AI Discovery
                discovered = self.analyzer.find_listing_links(data["website"], nav_links)
                ai_blog_url  = discovered.get("blog_url")
                ai_case_url  = discovered.get("case_study_url")
                ai_story_url = discovered.get("customer_story_url")

                # 2. Keyword Discovery (Deterministic Fallback)
                from extractors import _build_listing_targets
                kw_targets = _build_listing_targets(nav_links, data["website"])
                kw_blog_url = next((t["url"] for t in kw_targets if t["type"] == "blogs"), None)
                kw_case_url = next((t["url"] for t in kw_targets if t["type"] == "case_studies"), None)
                kw_story_url = next((t["url"] for t in kw_targets if t["type"] == "customer_stories"), None)

                # Merge: AI has priority, but Keywords act as safety net
                final_blog_url = ai_blog_url or kw_blog_url
                final_case_url = ai_case_url or kw_case_url
                final_story_url = ai_story_url or kw_story_url

                if final_blog_url:  print(f"[+] Discovered Blog Link: {final_blog_url}")
                if final_case_url:  print(f"[+] Discovered Case Study Link: {final_case_url}")
                if final_story_url: print(f"[+] Discovered Customer Story Link: {final_story_url}")

                # --- MANUAL OVERRIDE ---
                if manual_links:
                    if manual_links.get("blog_url"):
                        print(f"[*] Using manual blog link: {manual_links['blog_url']}", file=sys.stderr)
                        final_blog_url = manual_links["blog_url"]
                    if manual_links.get("case_study_url"):
                        print(f"[*] Using manual case study link: {manual_links['case_study_url']}", file=sys.stderr)
                        final_case_url = manual_links["case_study_url"]
                    if manual_links.get("customer_story_url"):
                        print(f"[*] Using manual customer story link: {manual_links['customer_story_url']}", file=sys.stderr)
                        final_story_url = manual_links["customer_story_url"]

                    for platform in ["instagram", "twitter", "facebook", "youtube"]:
                        if manual_links.get(f"{platform}_url"):
                            print(f"[*] Using manual {platform} link: {manual_links[f'{platform}_url']}", file=sys.stderr)
                            social_links[platform] = manual_links[f"{platform}_url"]

                # --- HYBRID DISCOVERY STRATEGY ---
                # Priority 1: Specialized Targets (Blogs, Case Studies, Stories)
                # This is our PRIMARY mission. We extract these first to ensure high-quality intelligence.
                if final_blog_url or final_case_url or final_story_url:
                    print(f"[*] PHASE 1: Specialized Discovery — Targeting Blogs/Case Studies...", file=sys.stderr)
                    external_data = extract_from_manual_links(self, final_blog_url, final_case_url, final_story_url)
                    merge_and_dedup(data, external_data)
                
                # Priority 2: Broad Fallback (Services, About, General Capabilities)
                # This only runs if Specialized content is missing or insufficient (< 3 items).
                # It ensures we never leave a trade website empty-handed.
                blog_count = len(data.get("blogs", []))
                case_count = len(data.get("case_studies", []))
                total_specialized = blog_count + case_count
                
                if total_specialized < 3:
                    reason = "missing" if total_specialized == 0 else "limited"
                    print(f"[*] PHASE 2: Broad Discovery ({reason}) — Extracting Services & General Content...", file=sys.stderr)
                    
                    # A. Service Discovery (Grabs specific service blocks from homepage/subpages)
                    homepage_services = extract_homepage_services(self, data["website"])
                    if homepage_services:
                        if "general_content" not in data: data["general_content"] = []
                        existing_titles = {str(item.get("title", "")).lower() for item in data["general_content"]}
                        for s in homepage_services:
                            if str(s.get("title", "")).lower() not in existing_titles:
                                data["general_content"].append(s)
                        
                        # Build overview if missing
                        if not data.get("overview") or "No overview" in data["overview"]:
                            titles = [s["title"] for s in homepage_services[:5] if s.get("title")]
                            if titles:
                                data["overview"] = f"Core services include: {', '.join(titles)}."
                    
                    # B. Universal Site Crawler (visits ALL internal pages, extracts every tag)
                    # Runs when service cards were insufficient or zero
                    # This NEVER returns empty — reads h1-h4, p, li, blockquote, contact info from every page
                    if len(data.get("general_content", [])) < 3 and total_specialized == 0:
                        print(f"[*] PHASE 3: Universal Site Crawler — visiting all internal pages...", file=sys.stderr)
                        universal_items = universal_site_crawler(self, data["website"], nav_links=nav_links)
                        if universal_items:
                            existing_titles = {str(i.get("title","")).lower() for i in data.get("general_content", [])}
                            for item in universal_items:
                                if str(item.get("title","")).lower() not in existing_titles:
                                    data["general_content"].append(item)
                            print(f"[+] Universal crawler added {len(universal_items)} items.", file=sys.stderr)

                        # --- AI OVERVIEW SYNTHESIS ---
                        # For sites with zero specialized content, we synthesize a robust 
                        # overview from the collected general content and service cards.
                        print(f"[*] Synthesizing final company overview from {len(data.get('general_content', []))} sources...", file=sys.stderr)
                        synthesized_overview = self.analyzer.build_overview_from_content(data["name"], data.get("general_content", []))
                        if synthesized_overview and len(synthesized_overview) > len(data.get("overview", "")):
                            data["overview"] = synthesized_overview
                            print(f"[+] Overview enriched via AI synthesis.", file=sys.stderr)
                            print(f"[+] Overview built from universal crawler content.", file=sys.stderr)

                        # Use AI to build clean overview from all collected content
                        if data.get("general_content") and (
                            not data.get("overview") or "No overview" in data.get("overview","")
                        ):
                            print(f"[*] Building AI overview from universal crawler content...", file=sys.stderr)
                            try:
                                ai_overview = self.analyzer.build_overview_from_content(
                                    data.get("name", ""), data["general_content"]
                                )
                                if ai_overview:
                                    data["overview"] = ai_overview
                                    print(f"[+] AI overview built: {ai_overview[:80]}...", file=sys.stderr)
                            except: pass

                        # Absolute last resort — AI describes company from URL alone
                        if not data.get("general_content") and (
                            not data.get("overview") or "No overview" in data.get("overview","")
                        ):
                            print(f"[*] Zero content found — using AI to describe company from URL...", file=sys.stderr)
                            try:
                                ai_overview = self.analyzer.extract_company_name_with_ai(data["website"])
                                data["overview"] = f"Company operating at {data['website']}. {ai_overview}"
                            except: pass
                else:
                    print(f"[+] Specialized Discovery successful ({total_specialized} items). Skipping general broad scan.", file=sys.stderr)

            except Exception as e:
                print(f"[*] AI Link Discovery warning: {e}", file=sys.stderr)
                try:
                    ext_data = extract_from_external_website(self, data["website"])
                    for k, v in ext_data.items(): data[k].extend(v)
                except: pass

            # Combine and deduplicate all items
            all_items = data["customer_stories"] + data["blogs"] + data["case_studies"] + data["general_content"]
            data["customer_stories"], data["blogs"], data["case_studies"], data["general_content"] = [], [], [], []
            seen_links = set()
            policy_patterns = ["privacy-policy", "cookie-policy", "terms-of-use", "term-of-use", "terms-and-conditions", "cookies-policy"]

            for item in all_items:
                link  = item["link"].rstrip("/")
                title = item.get("title", "").lower()
                dtype = item.get("detected_type")

                if link in seen_links: continue
                if any(p in link.lower() for p in policy_patterns) or \
                   (any(kw in title for kw in ["privacy", "cookie", "terms of use"]) and "policy" in title):
                    continue

                # Only skip contact/login/signup — allow /about, /team, /services through
                # These pages now contain real content from universal_site_crawler
                if any(kw in link.lower() for kw in ["/career", "/pricing", "/login", "/signup", "/cart", "/checkout"]):
                    continue

                if any(link.lower().endswith(p) for p in ["/blog", "/blogs", "/case-studies", "/case-study", "/success-stories"]):
                    continue

                seen_links.add(link)

                if dtype == "blogs":
                    data["blogs"].append(item)
                elif dtype == "customer_stories":
                    data["customer_stories"].append(item)
                elif dtype == "case_studies":
                    data["case_studies"].append(item)
                elif dtype == "general_content":
                    data["general_content"].append(item)
                elif any(kw in link.lower() for kw in ["/blog", "/article", "/insight"]):
                    data["blogs"].append(item)
                elif "zoho.com" in link.lower() or any(kw in link.lower() for kw in ["/customer-stor", "/testimonial"]):
                    data["customer_stories"].append(item)
                elif any(kw in link.lower() for kw in ["/case-stud", "/success-stor", "/portfolio"]):
                    if "workdrive" not in link.lower() and "drive.google" not in link.lower():
                        data["case_studies"].append(item)
                    if any(kw in link.lower() for kw in ["/resource", "/work"]) and "workdrive" not in link.lower():
                        data["case_studies"].append(item)
                else:
                    # Final catch-all for any other links found on listing pages
                    data["general_content"].append(item)

            # Limit and fetch content
            MAX_FETCH = 10
            for category in ["blogs", "case_studies", "customer_stories", "general_content"]:
                print(f"[*] Fetching content for top {MAX_FETCH} items in {category}...", file=sys.stderr)
                items_to_fetch  = data[category][:MAX_FETCH]
                data[category]  = items_to_fetch

                for item in items_to_fetch:
                    link = item["link"].lower().rstrip("/")
                    if item.get("content") or any(link.endswith(p) for p in ["/blog", "/blogs", "/case-studies", "/case-study", "/success-stories", "/resources"]):
                        if not item.get("content"):
                            item["content"] = "Listing page link - skipping direct content extraction."
                        continue

                    content = extract_page_content(self, item["link"])
                    if content:
                        item["content"] = self.analyzer.summarize_content(item.get("title", ""), content)
                    elif item.get("cardSnippet"):
                        # Use the snippet captured from the homepage/listing page card
                        item["content"] = f"(Summary from listing card) {item['cardSnippet']}"
                    else:
                        item["content"] = "Content extraction failed or page is empty."

            print(f"[+] Extraction complete: Found {len(data['customer_stories'])} stories, {len(data['blogs'])} blogs, {len(data['case_studies'])} case studies.", file=sys.stderr)
            print(f"[*] Finalizing data analysis...", file=sys.stderr)

            # ── FALLBACK TRIGGER ──────────────────────────────────────────────
            # If total own-site content is below threshold, run external signal collection
            # and score the company from fallback sources instead of penalising it unfairly.
            # general_content (service cards) also counts toward threshold now
            from extractors import check_content_threshold, run_fallback_data_collection

            # Count general_content items too — service cards = real content
            total_content = (len(data.get("blogs", [])) +
                             len(data.get("case_studies", [])) +
                             len(data.get("customer_stories", [])) +
                             len(data.get("general_content", [])))

            if total_content < 2:
                print(f"[!] Own-site content below threshold for '{data.get('name')}'. Triggering fallback...", file=sys.stderr)
                fallback_result = run_fallback_data_collection(
                    company_name=data.get("name", self.partner_name or "Unknown"),
                    website_url=data.get("website", ""),
                    linkedin_url=data.get("linkedin", "")
                )
                # Pass general_content and social_media into fallback so scorer can use them
                fallback_result["general_content"] = data.get("general_content", [])
                fallback_result["social_media"]    = data.get("social_media", {})

                # Score from fallback data using analyzer
                fallback_scores = self.analyzer.score_from_fallback_data(
                    company_name=data.get("name", self.partner_name or "Unknown"),
                    fallback=fallback_result
                )
                # Attach to data so storage.py can use it instead of content-based scoring
                data["fallback_scores"] = fallback_scores
                data["fallback_data"]   = fallback_result
            else:
                # Own-site content is sufficient — mark explicitly
                data["fallback_scores"] = None
                data["fallback_data"]   = None

        return data

    def _merge_items(self, original: list, new: list) -> list:
        seen_links = {item["link"].rstrip("/") for item in original if "link" in item and item["link"]}
        for item in new:
            link = item.get("link", "").rstrip("/")
            if link and link not in seen_links:
                original.append(item)
                seen_links.add(link)
        return original

    def _anchor_to_item(self, anchor) -> dict | None:
        try:
            title = anchor.inner_text().strip()
            href  = anchor.get_attribute("href") or ""
            if not title or not href or "javascript" in href.lower(): return None
            return {"title": title, "link": self._absolute_url(href)}
        except Exception: return None

    def _extract_items_from_section(self, section_keywords: list[str]) -> list[dict]:
        results = []
        heading_selectors = ["h2", "h3", "h4", ".section-title"]
        for h_sel in heading_selectors:
            for heading in self.page.query_selector_all(h_sel):
                try:
                    heading_text = heading.inner_text().strip().lower()
                    if not any(kw in heading_text for kw in section_keywords): continue
                    parent = heading.evaluate_handle("el => el.parentElement")
                    if parent:
                        anchors = parent.query_selector_all("a")
                        for anchor in anchors:
                            item = self._anchor_to_item(anchor)
                            if item: results.append(item)
                except Exception: continue
        return results

    def run(self) -> dict | list[dict]:
        with sync_playwright() as playwright:
            self._launch(playwright)
            try:
                if self.partner_name:
                    profile_url = self.find_partner()
                    try:
                        return self.extract_partner_data(profile_url, getattr(self, "manual_links", None))
                    except Exception as scrape_err:
                        err_msg = str(scrape_err).lower()
                        print(f"[-] CAPTURE FAILED: [*] Navigating directly to URL: {profile_url.upper()}", file=sys.stderr)
                        print(f"[-] Error during automated scrape: {scrape_err}", file=sys.stderr)

                        # Return a safe empty record instead of crashing
                        # Fallback scoring will handle it
                        from extractors import run_fallback_data_collection
                        company_name = self.partner_name if not self.partner_name.startswith("http") else profile_url
                        fallback_result = run_fallback_data_collection(
                            company_name=company_name,
                            website_url=profile_url,
                            linkedin_url=""
                        )
                        fallback_scores = self.analyzer.score_from_fallback_data(company_name, fallback_result)
                        return {
                            "partner_id": f"ext_{hashlib.md5(profile_url.encode()).hexdigest()[:12]}",
                            "name": company_name,
                            "overview": f"Scrape failed: {scrape_err}",
                            "website": profile_url,
                            "linkedin": None,
                            "customer_stories": [],
                            "blogs": [],
                            "case_studies": [],
                            "general_content": [],
                            "social_media": {"instagram": None, "twitter": None, "facebook": None, "youtube": None},
                            "parent_company": self.parent_company,
                            "fallback_scores": fallback_scores,
                            "fallback_data": fallback_result,
                            "scrape_status": "failed"
                        }
                else:
                    self.apply_filters()
                    return self.get_all_partners()
            finally:
                self._close()