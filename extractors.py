import sys
import re
import os
from urllib.parse import urljoin, urlparse

# Ensure bundled dependencies in temp_libs are accessible
temp_libs_path = os.path.join(os.path.dirname(__file__), "temp_libs")
if os.path.exists(temp_libs_path) and temp_libs_path not in sys.path:
    sys.path.insert(0, temp_libs_path)

from pypdf import PdfReader # pyrefly: ignore [missing-import] # type: ignore

def minify_text(text: str) -> str:
    """Collapses multiple spaces but preserves newlines and tabs as requested."""
    if not text: return ""
    # Remove literal spaces at the end of lines or before tabs
    text = re.sub(r' +(?=\n)', '', text)
    text = re.sub(r' +(?=\t)', '', text)
    # Remove literal spaces at the start of lines or after tabs
    text = re.sub(r'(?<=\n) +', '', text)
    text = re.sub(r'(?<=\t) +', '', text)
    # Collapse multiple literal spaces into one
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# ------------------------------------------------------------------ #
# Zoho Profile Extraction Functions (unchanged from original)
# ------------------------------------------------------------------ #

# Keywords that indicate we are blocked or hit a bot protection page
BLOCKED_KEYWORDS = [
    "access denied", "blocked", "cloudflare", "sucuri", "forbidden", 
    "captcha", "security check", "verify you are human", "pardon our interruption",
    "bot protection", "challenge-running", "403 forbidden", "site not accessible"
]

# ------------------------------------------------------------------ #
# SITE TYPE DETECTION — fast pre-checks before deep scraping
# ------------------------------------------------------------------ #

# Signals that strongly indicate a pure e-commerce / product site
# with no content marketing (blogs, case studies, customer stories)
ECOMMERCE_SIGNALS = [
    'add-to-cart', 'add_to_cart', 'addtocart',
    '/shop/', '/products/', '/collections/',
    '/cart', '/checkout', '/wishlist',
    'buy now', 'add to bag', 'add to basket',
    'out of stock', 'in stock', 'free shipping',
    'size guide', 'size chart', 'select size',
]

# Keywords that indicate content marketing IS present
CONTENT_SIGNALS = [
    '/blog', '/blogs', '/article', '/articles',
    '/case-stud', '/case_stud', '/customer-stor',
    '/success-stor', '/insight', '/resource',
    '/news', '/press', '/thought-leadership',
    '/whitepaper', '/ebook', '/webinar',
]

def is_ecommerce_site(page) -> bool:
    """
    Returns True if the page is a pure product/e-commerce site
    that almost certainly has no blogs, case studies, or customer stories.
    Used to skip deep scraping and jump straight to fallback.
    """
    try:
        body = page.content().lower()
        ecom_hits    = sum(1 for s in ECOMMERCE_SIGNALS if s in body)
        content_hits = sum(1 for s in CONTENT_SIGNALS if s in body)
        # 3+ e-commerce signals AND fewer than 2 content signals = skip deep scrape
        return ecom_hits >= 3 and content_hits < 2
    except Exception:
        return False

def has_content_signals_in_nav(nav_links: list) -> bool:
    """
    Returns True if any nav link suggests blogs/case studies/stories exist.
    Used to skip _expand_nav_fully on sites with no content marketing.
    """
    if not nav_links:
        return False
    content_kws = [
        '/blog', '/case', '/story', '/stories', '/resource',
        '/insight', '/news', '/article', '/whitepaper',
        '/press', '/media', '/learn', '/knowledge'
    ]
    return any(
        kw in link['href'].lower()
        for link in nav_links
        for kw in content_kws
    )


def is_page_blocked(agent) -> bool:
    """Checks if the current page indicates a block or bot protection."""
    try:
        title = agent.page.title().lower()
        if any(kw in title for kw in BLOCKED_KEYWORDS):
            return True
        
        # Check body text for common block patterns
        body_text = agent.page.locator("body").inner_text().lower()
        # Only check the first few hundred chars for speed
        if any(kw in body_text[:500] for kw in BLOCKED_KEYWORDS):
            return True
            
        return False
    except:
        return False

def extract_name(agent) -> str | None:
    # Check for block first
    if is_page_blocked(agent):
        print("[!] Block detected while extracting name. Skipping.", file=sys.stderr)
        return "Blocked Content"

    # Generic words that are likely NOT the company name itself
    LOCATIONS = ["india", "usa", "uk", "united states", "united kingdom", "australia", "canada", "singapore", "dubai", "london", "new york"]
    GENERICS = ["zoho consultant", "zoho partner", "welcome to", "home page", "about us", "contact us", "services"]
    
    # 1. Try specific partner selectors first
    selectors = [
        "h1.partner-name", "h1.partnerProfile__name",
        ".partner-profile h1", ".partnerCard__name",
        "a.navbar-brand", ".logo img[alt]", "img.logo[alt]"
    ]
    for sel in selectors:
        if "[alt]" in sel:
            base_sel = sel.split("[alt]")[0]
            try:
                el = agent.page.query_selector(base_sel)
                if el:
                    val = el.get_attribute("alt")
                    if val and len(val) > 1 and len(val) < 40:
                        lower_val = val.lower().strip()
                        if lower_val not in LOCATIONS and not any(g in lower_val for g in GENERICS):
                            return val.strip()
            except: pass
        else:
            val = agent._safe_text(sel)
            if val and (sel != "h1" or len(val) < 35):
                lower_val = val.lower().strip()
                if lower_val not in LOCATIONS and not any(generic in lower_val for generic in GENERICS):
                    return val.strip()
                
    # 2. Try page title cleaning
    try:
        title = agent.page.title()
        if title:
            # If we have a target name, look for the part that contains it
            search_target = agent.partner_name.lower() if agent.partner_name else ""
            
            for sep in ['|', '-', '—', ':']:
                if sep in title:
                    parts = [p.strip() for p in title.split(sep)]
                    # Priority 1: Part that contains our search target
                    if search_target:
                        for p in parts:
                            if search_target in p.lower() and len(p) < 40:
                                return p
                    
                    # Priority 2: Use the part that isn't a generic location
                    for p in parts:
                        low_p = p.lower()
                        if len(p) > 1 and len(p) < 35 and low_p not in LOCATIONS and not any(g in low_p for g in GENERICS):
                            return p
                            
            if len(title) < 40:
                lower_title = title.lower()
                if lower_title not in LOCATIONS and not any(generic in lower_title for generic in GENERICS):
                    return title.strip()
    except: pass

    return agent.partner_name or "Unknown Partner"


def extract_overview(agent) -> str | None:
    # Check for block first
    if is_page_blocked(agent):
        return "Scrape Failed: Access Denied / Blocked Content"

    selectors = [
        ".partner-overview", ".partnerProfile__overview",
        ".about-partner p", ".partner-description",
        "[class*='overview']", "[class*='description'] p",
        ".partner-about", "section.about p", "#overview", "#about",
        ".hero__content", ".hero-text", "main p", ".content p"
    ]
    final_text = None
    for sel in selectors:
        val = agent._safe_text(sel)
        if val and len(val) > 20:
            final_text = minify_text(val)
            break
            
    # Try meta description if no overview found yet
    if not final_text:
        try:
            meta_desc = agent.page.locator("meta[name='description']").get_attribute("content")
            if meta_desc and len(meta_desc) > 20:
                final_text = minify_text(meta_desc)
        except Exception: pass

    # Last resort — grab first meaningful paragraph from body text
    # Catches small/local business sites that have no structured overview
    if not final_text:
        try:
            paragraphs = agent.page.locator("p").all()
            for p in paragraphs[:20]:
                try:
                    txt = p.inner_text().strip()
                    # Skip nav/footer noise — only take real sentences
                    if len(txt) > 60 and len(txt.split()) > 8:
                        final_text = minify_text(txt[:400])
                        break
                except: continue
        except Exception: pass

    # ECOSYSTEM SCAN: Look for major global partner names to prevent AI from assuming 'lack of partnerships'
    try:
        page_text = agent.page.locator("body").inner_text()
        found_partners = []
        for p_name in ["AWS", "Amazon Web Services", "Microsoft", "Azure", "Google Cloud", "GCP", "SAP", "Oracle", "Salesforce", "ServiceNow", "IBM"]:
            if re.search(rf'\b{re.escape(p_name)}\b', page_text, re.I):
                found_partners.append(p_name)
        if found_partners:
            final_text = f"{final_text}\n[Ecosystem Evidence Found: {', '.join(sorted(list(set(found_partners))))}]"
    except: pass

    return final_text if final_text else None


def extract_website(agent) -> str | None:
    website_selectors = [
        "a.zwc-pr-weblink", "a[href*='visit'][class*='website' i]",
        "a.partner-website", "a[class*='website']",
    ]
    for sel in website_selectors:
        href = agent._safe_attr(sel, "href")
        if href:
            return agent._absolute_url(href)
    for anchor in agent.page.query_selector_all("a[href]"):
        try:
            href = anchor.get_attribute("href") or ""
            text = anchor.inner_text().strip().lower()
            if (
                href.startswith("http")
                and "zoho.com" not in href
                and "linkedin.com" not in href
                and "twitter.com" not in href
                and "facebook.com" not in href
                and ("website" in text or "visit" in text or "www" in href)
            ):
                return href
        except Exception:
            continue
    return None


def extract_linkedin(agent) -> str | None:
    ln_el = agent.page.query_selector("a.zwc-pr-linkedin")
    if ln_el:
        href = ln_el.get_attribute("href")
        if href:
            return agent._absolute_url(href)
            
    # Fallback: Search for any LinkedIn link on the page, excluding Zoho's corporate links
    for anchor in agent.page.query_selector_all("a[href*='linkedin.com']"):
        try:
            href = anchor.get_attribute("href")
            if href:
                abs_url = agent._absolute_url(href)
                # Filter out known Zoho corporate LinkedIn profiles
                if abs_url and not any(x in abs_url.lower() for x in ["zoho-partner-program", "company/zoho", "/zoho"]):
                    return abs_url
        except Exception:
            continue
    return None


def extract_linkedin_from_external(agent, website_url: str) -> str | None:
    """Attempt to find a LinkedIn link on the partner's own website."""
    print(f"[*] Attempting to find LinkedIn on {website_url}...", file=sys.stderr)
    try:
        # We assume the page is already loaded or we load it
        if agent.page.url != website_url:
            agent._safe_goto(website_url, timeout=45000)
            agent.page.wait_for_timeout(2000)
        
        # Check footer and header specifically first
        containers = agent.page.locator("footer, header, .footer, .header, .social").all()
        for container in containers:
            ln_link = container.locator("a[href*='linkedin.com']").first
            if ln_link.count() > 0:
                href = ln_link.get_attribute("href")
                if href and "linkedin.com/company/" in href:
                    return href
        
        # General search on the page
        anchors = agent.page.locator("a[href*='linkedin.com/company/']").all()
        for a in anchors:
            href = a.get_attribute("href")
            if href: return href
            
    except Exception as e:
        print(f"[*] Warning: External LinkedIn extraction failed: {e}", file=sys.stderr)
    return None



def extract_customer_stories(agent) -> list:
    print("[*] Switching to Customer Stories tab...", file=sys.stderr)
    try:
        tab_selectors = [
            "text='Customer Stories'",
            "li:has-text('Customer Stories')",
            "div:has-text('Customer Stories')"
        ]
        tab_clicked = False
        for sel in tab_selectors:
            tab = agent.page.locator(sel).first
            if tab.count() > 0:
                tab.click()
                tab_clicked = True
                break
        if tab_clicked:
            agent.page.wait_for_timeout(4000)
            agent._scroll_to_bottom()

        results = []
        # 1. Try specific patterns and general cards inside the tab
        story_links = agent.page.locator(
            "a[href*='/customers/'], a[href*='FileDownloadPublic'], a[href*='customer-story'], "
            ".zp-customer-stories-tab-content a, .customer-stories a, .story-card a, .case-study-card a, "
            ".zwc-tab-section.active a, .zwc-pr-tab-content.active a"
        ).all()
        for link in story_links:
            try:
                href = link.get_attribute("href")
                title = link.inner_text().strip()
                if not title:
                    title = link.locator("xpath=..").inner_text().split("\n")[0].strip()
                if title and href and len(title) > 3:
                    item = {"title": title, "link": agent._absolute_url(href), "detected_type": "customer_stories"}
                    if item not in results:
                        results.append(item)
            except Exception:
                continue

        if not results:
            containers = agent.page.locator(
                ".zp-customer-stories-tab-content, .zwc-pr-customer-stories, .customer-stories, .zp-tab-panel:not(.hide), .zwc-tab-section.active, .zwc-casestudy-sec"
            ).all()
            for container in containers:
                anchors = container.locator("a").all()
                for a in anchors:
                    item = agent._anchor_to_item(a)
                    if item:
                        item["detected_type"] = "customer_stories"
                        if item not in results:
                            results.append(item)
        
        # 3. Final fallback: look for card-like elements in the whole page if tab was clicked
        if not results and tab_clicked:
             cards = agent.page.locator("[class*='customer-story' i], [class*='testimonial' i]").all()
             for card in cards:
                 anchors = card.locator("a").all()
                 for a in anchors:
                     item = agent._anchor_to_item(a)
                     if item:
                         item["detected_type"] = "customer_stories"
                         if item not in results:
                             results.append(item)

        return results
    except Exception as e:
        print(f"[*] Warning: Error in extract_customer_stories: {e}", file=sys.stderr)
    
    results = agent._extract_items_from_section(
        ["customer stor", "testimonial", "success stor", "client stor"]
    )
    for item in results:
        item["detected_type"] = "customer_stories"
    return results


def extract_blogs(agent) -> list:
    try:
        tab = agent.page.locator(
            "ul.zwc-pr-tab li:has-text('Blog'), li:has-text('Blogs')"
        ).first
        if tab.count() > 0:
            tab.click()
            agent.page.wait_for_timeout(2000)
            results = []
            anchors = agent.page.locator(
                ".zwc-pr-tab-content.active a, .zwc-pr-blog-list a"
            ).all()
            for a in anchors:
                item = agent._anchor_to_item(a)
                if item:
                    item["detected_type"] = "blogs"
                    results.append(item)
            if results:
                return results
    except Exception:
        pass
    results = agent._extract_items_from_section(["blog", "article", "post"])
    for item in results:
        item["detected_type"] = "blogs"
    return results


def extract_case_studies(agent) -> list:
    print("[*] Switching to Case Studies tab...", file=sys.stderr)
    try:
        tab_selectors = ["a:has-text('Case Studies')", "li:has-text('Case Studies')"]
        tab_clicked = False
        for sel in tab_selectors:
            tab = agent.page.locator(sel).first
            if tab.count() > 0:
                try:
                    tab.click(timeout=5000)
                    tab_clicked = True
                    break
                except Exception: continue

        if tab_clicked:
            agent.page.wait_for_timeout(3000)
            agent._scroll_to_bottom()
            results = []
            anchors = agent.page.locator(".zwc-pr-tab-content.active a, .zwc-tab-section.active a").all()
            for a in anchors:
                item = agent._anchor_to_item(a)
                if item:
                    item["detected_type"] = "case_studies"
                    results.append(item)
            if results:
                return results
    except Exception:
        pass

    results = _extract_by_class_or_id(agent, ["case-stud", "casestud", "case_stud", "success-stor"])
    if results:
        for item in results:
            item["detected_type"] = "case_studies"
        return results
    
    results = agent._extract_items_from_section(["case stud", "case-stud"])
    for item in results:
        item["detected_type"] = "case_studies"
    return results


def _extract_by_class_or_id(agent, keywords: list[str]) -> list[dict]:
    results = []
    try:
        agent.page.evaluate("""
            () => {
                const potentialCards = document.querySelectorAll('div, section, article, li');
                potentialCards.forEach(el => {
                    const classStr = el.className && typeof el.className === 'string'
                        ? el.className.toLowerCase() : '';
                    if (classStr.includes('card') || classStr.includes('item') ||
                        classStr.includes('study') || classStr.includes('post')) {
                        el.dispatchEvent(new MouseEvent('mouseover', {
                            view: window, bubbles: true, cancelable: true
                        }));
                    }
                });
            }
        """)
        agent.page.wait_for_timeout(1000)

        items = agent.page.evaluate(f"""
            (keywords) => {{
                const results = [];
                document.querySelectorAll('*').forEach(el => {{
                    const classStr = el.className && typeof el.className === 'string'
                        ? el.className.toLowerCase() : '';
                    const idStr = el.id ? el.id.toLowerCase() : '';
                    if (keywords.some(kw => classStr.includes(kw) || idStr.includes(kw))) {{
                        // Anti-Mixing Check: If we found a 'case study' class but the heading says 'Customer Stories', skip it.
                        const heading = el.querySelector('h1,h2,h3,h4,h5,h6, [class*="title" i], [class*="heading" i]');
                        const hText = heading ? heading.innerText.toLowerCase() : '';
                        if (keywords.some(k => k.includes('case')) && hText.includes('customer stor')) return;
                        if (keywords.some(k => k.includes('customer')) && hText.includes('case stud')) return;

                        if (el.tagName === 'A') {{
                            results.push({{ title: el.innerText.trim(), link: el.href }});
                        }} else {{
                            el.querySelectorAll('a').forEach(a => {{
                                let aText = a.innerText.trim();
                                const href = a.href;
                                if (aText.toLowerCase().includes('read more') ||
                                    aText.toLowerCase().includes('view more') ||
                                    aText.length < 3) {{
                                    if (heading) aText = heading.innerText.trim();
                                    else if (el.innerText.trim().length > 10)
                                        aText = el.innerText.split('\\n')[0].trim();
                                }}
                                if (aText.length > 2) results.push({{ title: aText, link: href }});
                            }});
                        }}
                    }}
                }});
                return results;
            }}
        """, keywords)

        for item in items:
            if item.get("link"):
                abs_url = agent._absolute_url(item["link"])
                if abs_url and abs_url.startswith("http"):
                    results.append({"title": item["title"], "link": abs_url})
            elif item.get("content"):
                results.append(item)
    except Exception as e:
        print(f"[*] Warning: Error in _extract_by_class_or_id: {e}", file=sys.stderr)
    return results


def _try_extract_pdf(path: str) -> str | None:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            print(f"[*] PDF is encrypted/password-protected, skipping.", file=sys.stderr)
            return None
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip() if len(text.strip()) > 50 else None
    except Exception as e:
        print(f"[*] PDF read error: {e}", file=sys.stderr)
        return None


def extract_page_content(agent, url: str) -> str | None:
    print(f"[*] Fetching content from: {url}", file=sys.stderr)
    is_download_url = any(p in url.lower() for p in [
        "filedownload", "store.zoho.com", ".pdf", "/download", "file_id="
    ])

    if is_download_url:
        temp_path = os.path.join(os.getcwd(), "temp_scraper_dl.pdf")
        try:
            with agent.page.expect_download(timeout=30000) as dl_info:
                try:
                    agent._safe_goto(url, timeout=45000)
                except Exception as e:
                    if "Download is starting" not in str(e) and "net::ERR" not in str(e):
                        raise e
            download = dl_info.value
            if download:
                download.save_as(temp_path)
                text = _try_extract_pdf(temp_path)
                if text:
                    return text
                print(f"[*] Downloaded file is not a readable PDF.", file=sys.stderr)
                return None
        except Exception as e:
            print(f"[*] Download failed for {url}: {e}", file=sys.stderr)
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    try:
        response = agent._safe_goto(url, wait_until="domcontentloaded", timeout=25000)
        
        if response and response.status >= 400:
            print(f"[*] Warning: Got status {response.status} for {url}", file=sys.stderr)
            if response.status in [403, 429]:
                return f"Scrape Failed: Blocked by server (Status {response.status})"

        agent.page.wait_for_timeout(3000)
        
        # Check for bot protection pages
        if is_page_blocked(agent):
            print(f"[!] Access Denied/Block detected for {url}", file=sys.stderr)
            return f"Scrape Failed: Access Denied / Bot Protection on {url}"

        content = agent.page.evaluate("""
            () => {
                // Specialized handling for YouTube
                if (window.location.href.includes('youtube.com/watch')) {
                    const desc = document.querySelector('#description-inline-expander');
                    if (desc) return desc.innerText.trim();
                    const snippet = document.querySelector('yt-formatted-string#description-text');
                    if (snippet) return snippet.innerText.trim();
                }

                const excludes = [
                    'nav','footer','header','aside','.navbar','.footer','.header',
                    '.menu','.sidebar','.ad','.ads','.social-share','.related-posts',
                    '#navbar','#footer','#header','.top-bar','.bottom-bar',
                    '.cookie-banner', '.gdpr', '.banner-ad',
                    'script','style','iframe','noscript','svg','button','[role="button"]'
                ];
                
                const clone = document.body.cloneNode(true);
                excludes.forEach(selector => {
                    clone.querySelectorAll(selector).forEach(el => el.remove());
                });

                // Priority containers for main content
                const mainSelectors = [
                    'article', 'article.post', 'main', 'main#main', '.post-content', '.blog-content',
                    '.entry-content', '.content', '#content', '.article-body',
                    '.case-study-content', '.zp-customer-story-content',
                    '.elementor-widget-theme-post-content', '.elementor-widget-container', 
                    '.elementor-text-editor', '.elementor-section', '.wp-block-group', '.entry-content-single',
                    '.zpblog-post-content', '.zpcontent', '.zptext',
                    '#primary .site-main', '.content-area',
                    '.zpcontent-container', '.theme-content-area-inner', '.theme-content-container',
                    '.wp-block-post-content', '.hubspot-content', '.post-body', '.article-content',
                    '.vc_column-inner .wpb_wrapper', '.site-content', '.wd-content-area', '.woodmart-entry-content'
                ];
                
                // Aggregation Strategy:
                // 1. Try to find the best container and collect all text from its relevant children
                // 2. If no single best container, aggregate all elements matching main selectors
                
                let aggregatedContent = [];
                let seenTexts = new Set();

                // Try each selector and collect all matching elements
                for (const selector of mainSelectors) {
                    const elements = clone.querySelectorAll(selector);
                    elements.forEach(el => {
                        // Check if this element is nested inside an already collected one
                        let isNested = false;
                        for (let other of elements) {
                            if (other !== el && other.contains(el)) {
                                isNested = true;
                                break;
                            }
                        }
                        if (isNested) return;

                        const text = el.innerText.trim();
                        if (text.length > 50 && !seenTexts.has(text)) {
                            aggregatedContent.push(text);
                            seenTexts.add(text);
                        }
                    });
                    
                    // If we found significant content with a high-priority selector, stop and use it
                    const totalLen = aggregatedContent.join('\\n\\n').length;
                    if (totalLen > 300) break; 
                }
                
                if (aggregatedContent.length > 0) {
                    const result = aggregatedContent.join('\\n\\n');
                    if (result.length > 100) return result;
                }

                // Fallback: Paragraphs aggregation
                const paragraphs = Array.from(clone.querySelectorAll('p, .zptext, div.zprow'));
                if (paragraphs.length > 0) {
                    const pText = paragraphs
                        .map(p => p.innerText.trim())
                        .filter(t => t.length > 25)
                        .join('\\n\\n');
                    if (pText.length > 100) return pText;
                }

                // Final Fallback: Body text
                const bodyText = clone.innerText.trim();
                if (bodyText.length > 80) return bodyText;

                return null;
            }
        """)
        return minify_text(content) if content and len(content) > 30 else None
    except Exception as e:
        print(f"[*] Warning: Could not extract content from {url}: {e}", file=sys.stderr)
        return None



# ------------------------------------------------------------------ #
# IMPROVED: External Website Extraction
# ------------------------------------------------------------------ #

# Keywords used for categorisation (shared between nav scan & article scan)
BLOG_URL_KW  = ["/blog", "/blogs", "/article", "/articles", "/insight",
                "/insights", "/news", "/post", "/posts", "/updates", "/press",
                "blog-post", "news-item", "/knowledge-hub", "/resources/blog"]
CASE_URL_KW  = ["/case-stud", "/case_stud", "/portfolio", "/use-case", "/use_case", 
                "/references", "casestudy", "case-study", "/impact", "/work-gallery", "/case-studies"]
STORY_URL_KW = ["/success-stor", "/success_stor", "/client-stor", "/client_stor", 
                "/customers", "success-story", "successstory", "customer-story",
                "customer-stories", "/testimonials"]
INFO_URL_KW  = ["/about", "/services", "/service/", "/solutions", "/industries", 
                "/expertise", "/platform", "/products", "/why-us", "/company",
                "/what-we-do", "/our-approach", "/methodology", "/implementation",
                "/projects", "/sectors", "/capabilities", "/applications", "/gallery",
                "/our-work", "/process", "/how-we-work", "/our-story", "/our-services"]

BLOG_TEXT_KW = ["blog", "article", "insight", "news", "post", "update", "press", "journal", "thoughts"]
CASE_TEXT_KW = ["case study", "case studies", "case-study", "portfolio", "use case", "references", "our work", "projects", "impact", "galleries"]
STORY_TEXT_KW = ["success story", "success stories", "client story", "client stories", 
                 "customer story", "customer stories", "successstory", "testimonial", "clients say", "reviews", "feedback"]
INFO_TEXT_KW  = ["about", "service", "solution", "industry", "expertise", "platform", "product", "why us", "company", "what we do", "our approach", "methodology", "implementation", "sectors", "capabilities", "applications", "process", "our story", "how we help", "our services"]
# Nav items whose text/href suggests a container menu (Resources, More, Solutions…)
CONTAINER_KW = ["resource", "resources", "more", "solutions", "learn",
                "library", "knowledge", "media", "content", "company", "stories", "insights", "expertise",
                "sectors", "capabilities", "services", "industries"]

DATE_REGEX = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+\d{1,2},?\s+\d{4}$", re.I
)
GENERIC_LINK_TEXT = {"read more", "view more", "learn more",
                     "click here", "→", "»", "see more", "explore",
                     "continue reading"}
BAD_URL_PATTERNS = [
    "workdrive", "store.zoho", "drive.google", "dropbox",
    "filedownload", ".pdf", ".doc", ".ppt", ".xls",
    "/contact", "/about", "/pricing", "/login", "/signup", "/signin",
    "/tag/", "/category/", "/author/", "/page/", "/feed", "/rss",
    "/privacy", "/terms", "/cookie", "/legal", "/security",
    "javascript:", "mailto:", "tel:",
]


def _categorise_by_url(url: str) -> str | None:
    """Return 'blogs', 'case_studies', 'customer_stories' or 'general_content' based on URL patterns."""
    lower = url.lower()
    if any(k in lower for k in STORY_URL_KW): return 'customer_stories'
    if any(k in lower for k in CASE_URL_KW): return 'case_studies'
    if any(k in lower for k in BLOG_URL_KW): return 'blogs'
    if any(k in lower for k in INFO_URL_KW): return 'general_content'
    return None


def _categorise_by_text(text: str) -> str | None:
    """Return 'blogs', 'case_studies', 'customer_stories' or 'general_content' based on link text."""
    lower = text.lower()
    if any(k in lower for k in STORY_TEXT_KW): return 'customer_stories'
    if any(k in lower for k in CASE_TEXT_KW): return 'case_studies'
    if any(k in lower for k in BLOG_TEXT_KW): return 'blogs'
    if any(k in lower for k in INFO_TEXT_KW): return 'general_content'
    return None


def _expand_nav_fully(page) -> None:
    """
    Click / hover every nav-level toggle, dropdown trigger, and 'More' button
    so that hidden sub-menus are rendered in the DOM before we scrape links.

    Strategy:
      1. Hover all nav <li> and <button> elements (reveals CSS :hover menus).
      2. Click elements whose text is a known container keyword (Resources, More…).
      3. Wait for any JS animations to settle.
      4. Repeat once more for deeply nested menus (e.g. mega-menus).
    """
    js = """
        async () => {
            const NAV_SELECTORS = [
                'nav', 'header', '.navbar', '.nav', '.menu',
                '.navigation', '[role="navigation"]',
                '.header-nav', '.site-nav', '.main-nav',
                '#navbar', '#header-menu', '#main-menu',
            ];
            const CONTAINER_KW = [
                'resource', 'resources', 'more', 'solutions', 'learn',
                'library', 'knowledge', 'media', 'content', 'company',
                'services', 'products', 'platform', 'tools',
            ];

            function dispatchHover(el) {
                ['mouseover', 'mouseenter', 'focus'].forEach(evt =>
                    el.dispatchEvent(new MouseEvent(evt, { bubbles: true }))
                );
            }

            // Collect all candidate nav elements
            const seen = new Set();
            const candidates = [];
            NAV_SELECTORS.forEach(sel => {
                document.querySelectorAll(
                    sel + ' li, ' + sel + ' button, ' +
                    sel + ' [class*="dropdown"], ' +
                    sel + ' [class*="toggle"], ' +
                    sel + ' [class*="menu-item"], ' +
                    sel + ' [class*="nav-item"], ' +
                    sel + ' [class*="more"]'
                ).forEach(el => {
                    if (!seen.has(el)) { seen.add(el); candidates.push(el); }
                });
            });

            // Pass 1: hover everything to reveal CSS-driven dropdowns
            candidates.forEach(dispatchHover);
            await new Promise(r => setTimeout(r, 600));

            // Pass 2: click container-keyword elements to open JS-driven menus
            candidates.forEach(el => {
                const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                const isContainer = CONTAINER_KW.some(kw => t === kw || t.startsWith(kw));
                const hasArrow = el.querySelector(
                    'svg, .arrow, .caret, .chevron, [class*="arrow"], [class*="caret"]'
                );
                const hasToggle = el.getAttribute('aria-haspopup') ||
                                  el.getAttribute('aria-expanded') !== null ||
                                  el.getAttribute('data-toggle');
                if (isContainer || hasArrow || hasToggle) {
                    dispatchHover(el);
                    try { el.click(); } catch(e) {}
                }
            });
            await new Promise(r => setTimeout(r, 800));

            // Pass 3: hover/click newly visible elements (for nested mega-menus)
            const newCandidates = [];
            candidates.forEach(el => {
                el.querySelectorAll('li, button, a').forEach(child => {
                    if (!seen.has(child)) { seen.add(child); newCandidates.push(child); }
                });
            });
            newCandidates.forEach(dispatchHover);
            await new Promise(r => setTimeout(r, 500));
        }
    """
    try:
        page.evaluate(js)
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"[*] Warning: nav expansion error: {e}", file=sys.stderr)


def _collect_all_nav_links(page, base_domain: str) -> list[dict]:
    """
    Collect every visible link from nav / header / footer after menus are expanded.
    Returns list of {text, href}.
    """
    return page.evaluate("""
        (baseDomain) => {
            const links = [];
            const seen = new Set();
            
            // 1. Structural targets (high priority)
            const SELECTORS = [
                'nav a', 'header a', 'footer a', '.navbar a', '.nav a', '.menu a',
                '.navigation a', '[role="navigation"] a', '.header-nav a', '.site-nav a',
                '.main-nav a', '#navbar a', '#header-menu a', '#main-menu a',
                '.wd-nav-main a', '.woodmart-nav-link a', '.wd-main-menu a',
                '.zpmenu a', '.zpnavbar a', '.zpheader a', '[class*="zpmenu"] a',
                '[class*="dropdown"] a', '[class*="submenu"] a',
                '[class*="mega-menu"] a', '[class*="flyout"] a',
                '[aria-expanded] + * a', '[data-toggle] + * a',
            ];
            
            // 2. Broad search: Grab EVERYTHING that looks like an internal link
            // This is the "Safety Net" for sites with unconventional structures.
            const allAnchors = Array.from(document.querySelectorAll('a[href]'));
            
            allAnchors.forEach(a => {
                const href = a.href || '';
                const text = (a.textContent || a.innerText || '').trim();
                
                if (!href || seen.has(href)) return;
                
                // Filtering
                const lowerHref = href.toLowerCase();
                const isInternal = lowerHref.includes(baseDomain) || 
                                   (!lowerHref.startsWith('http') && !lowerHref.startsWith('//'));
                
                if (!isInternal) return;
                if (lowerHref.includes('#') || lowerHref.includes('javascript:') || lowerHref.includes('mailto:')) return;
                
                // Is it in a known nav/structural container?
                let inNav = false;
                for (const sel of SELECTORS) {
                    if (a.closest(sel)) { inNav = true; break; }
                }
                
                // If not in a known nav, only include if it looks like a menu item (short text)
                // or if it's in the top/bottom 15% of the page height (header/footer guess)
                if (!inNav) {
                    const rect = a.getBoundingClientRect();
                    const pageHeight = document.documentElement.scrollHeight;
                    const isTopOrBottom = rect.top < (pageHeight * 0.2) || rect.top > (pageHeight * 0.8);
                    const isShort = text.length > 2 && text.length < 40;
                    if (!isTopOrBottom && !isShort) return;
                }

                seen.add(href);
                links.push({ text: text.toLowerCase(), href });
            });
            
            return links;
        }
    """, base_domain)


def _build_listing_targets(nav_links: list[dict], site_url: str) -> list[dict]:
    """
    From nav links decide which pages are listing pages for blogs / case studies.
    Returns list of {url, type} where type ∈ {'blogs', 'case_studies', 'generic'}.

    Logic (priority order):
      1. URL pattern  → direct match to BLOG_URL_KW / CASE_URL_KW
      2. Link text    → match to BLOG_TEXT_KW / CASE_TEXT_KW
      3. Container kw → link text is a known resource hub (Resources, Library…) → generic
         BUT only if the URL itself also looks like a hub (not a specific service page)
    """
    UTILITY_URL_KW = [
        '/contact', '/pricing', '/career', '/job', '/jobs',
        '/privacy', '/terms', '/login', '/signup',
        '/support', '/help', '/faq',
    ]

    def is_utility_url(url: str) -> bool:
        lower = url.lower()
        return any(kw in lower for kw in UTILITY_URL_KW)

    targets = []
    seen_urls = set()

    for item in nav_links:
        href = item["href"]
        text = item["text"]
        norm = href.rstrip("/")
        if norm in seen_urls:
            continue

        # Skip utility pages immediately — they are never informative targets
        if is_utility_url(href):
            continue

        cat = _categorise_by_url(href) or _categorise_by_text(text)

        if cat is None:
            # Only mark as generic if the link TEXT looks like a resource hub
            # AND the URL itself is a short/hub-style path (not a deep service page)
            is_hub_text = any(k in text for k in CONTAINER_KW)
            url_depth = len([p for p in href.rstrip('/').split('/') if p]) 
            is_short_path = url_depth <= 4  # e.g. trigya.co/resources is depth 1
            if is_hub_text and is_short_path:
                cat = "generic"
            else:
                continue  # Not relevant

        seen_urls.add(norm)
        targets.append({"url": href, "type": cat})
        print(f"[*]   [{cat}] nav target: {href!r}  (text={text!r})", file=sys.stderr)

    # Fallback: try well-known paths if nothing found
    if not targets:
        print("[*] No nav targets found, trying common paths.", file=sys.stderr)
        for path, ltype in [
            ("/blog", "blogs"), ("/blog/", "blogs"), ("/blogs", "blogs"), ("/articles", "blogs"),
            ("/insights", "blogs"), ("/news", "blogs"),
            ("/case-studies", "case_studies"), ("/case-studies/", "case_studies"),
            ("/case-studies-1", "case_studies"), ("/case-studies-1/", "case_studies"),
            ("/success-stories", "case_studies"), ("/success-stories/", "case_studies"),
            ("/customers", "case_studies"), ("/portfolio", "case_studies"),
            ("/resources", "generic"), ("/insights", "blogs"),
            ("/cases", "case_studies"), ("/case-study", "case_studies"),
        ]:
            targets.append({"url": urljoin(site_url, path), "type": ltype})

    # Prioritize specific categories over 'general' and 'generic'
    priority_order = {"blogs": 0, "case_studies": 0, "customer_stories": 0, "general_content": 1, "generic": 2}
    targets.sort(key=lambda x: priority_order.get(x["type"], 3))

    return targets


def _collect_articles_from_listing(agent, listing_url: str,
                                   base_domain: str, page_default_cat: str | None,
                                   strict_path_filter: bool = False) -> list[dict]:
    """
    Open a listing page, trigger any lazy-load / hover reveals,
    then harvest all article links with best-effort title and category.
    Returns list of {title, link, detectedCategory}.
    """
    try:
        resp = agent._safe_goto(listing_url, wait_until="domcontentloaded", timeout=25000)
        if resp and resp.status >= 400:
            print(f"[*]   HTTP {resp.status} for {listing_url}, skipping.", file=sys.stderr)
            return []
        agent.page.wait_for_timeout(2000)
        agent._scroll_to_bottom()

        # Trigger hover reveals on card elements
        agent.page.evaluate("""
            () => {
                document.querySelectorAll(
                    'div, li, article, section, a, .card, [class*="post"], [class*="item"]'
                ).forEach(el => {
                    el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                });
            }
        """)
        agent.page.wait_for_timeout(800)

        # Scroll again in case new cards loaded
        agent._scroll_to_bottom()
        agent.page.wait_for_timeout(600)

    except Exception as e:
        print(f"[*]   Could not load listing {listing_url}: {e}", file=sys.stderr)
        return []

    return agent.page.evaluate(r"""
        (args) => {
            const { baseDomain, listingUrl, pageDefaultCat, strictPathFilter,
                    BLOG_URL_KW, CASE_URL_KW, STORY_URL_KW,
                    BLOG_TEXT_KW, CASE_TEXT_KW, STORY_TEXT_KW,
                    BAD_URL_PATTERNS, GENERIC_LINK_TEXT, DATE_REGEX_SRC } = args;

            const DATE_RE = new RegExp(DATE_REGEX_SRC, 'i');
            const GENERIC_SET = new Set(GENERIC_LINK_TEXT);

            function catByUrl(url) {
                const l = url.toLowerCase();
                if (STORY_URL_KW.some(k => l.includes(k))) return 'customer_stories';
                if (CASE_URL_KW.some(k => l.includes(k))) return 'case_studies';
                if (BLOG_URL_KW.some(k => l.includes(k))) return 'blogs';
                return null;
            }
            function catByText(text) {
                const l = text.toLowerCase();
                if (STORY_TEXT_KW.some(k => l.includes(k))) return 'customer_stories';
                if (CASE_TEXT_KW.some(k => l.includes(k))) return 'case_studies';
                if (BLOG_TEXT_KW.some(k => l.includes(k))) return 'blogs';
                return null;
            }

            // ── Shared helpers ───────────────────────────────────────────────
            const mainContent = document.body;
            const results = [];
            const seen = new Set();
            const normListing = listingUrl.replace(/\/$/, '');

            // URLs that are definitely NOT articles (service pages, nav, etc.)
            const BAD_PATH_PATTERNS = [
                '/about', '/contact', '/pricing',
                '/login', '/signup', '/signin', '/job', '/career', '/jobs',
                '/tag/', '/category/', '/author/', '/page/', '/feed',
                '/privacy', '/terms', '/cookie', '/legal',
                '/implementation', '/accounting', '/consulting', '/development',
                '/marketing', '/solutions', '/products', '/platform',
                'javascript:', 'mailto:', 'tel:', '.pdf',
            ];
            function isBadUrl(url) {
                const l = url.toLowerCase();
                return BAD_PATH_PATTERNS.some(p => l.includes(p));
            }
            function addResult(href, title, cat, snippet) {
                if (!href || !href.startsWith('http') || !href.includes(baseDomain)) return;
                if (isBadUrl(href)) return;
                const norm = href.replace(/\/$/, '');
                if (norm === normListing || seen.has(norm)) return;
                seen.add(norm);
                const finalTitle = (title || '').split('\n')[0].trim();
                if (finalTitle.length < 5) return;
                // catByUrl gives the most reliable signal; then the listing page's own category;
                // final fallback: 'case_studies' is safer than 'blogs' for slug-only URLs
                const resolvedCat = catByUrl(href) || pageDefaultCat || (pageDefaultCat === 'general_content' ? 'general_content' : 'case_studies');
                
                results.push({
                    title: finalTitle,
                    link: href,
                    detectedCategory: resolvedCat,
                    cardSnippet: (snippet || '').substring(0, 1000).trim()
                });
            }

            // ── PASS 1: WordPress / flat-heading pattern ─────────────────────
            // Handles blog pages like trigya.co/blog where each post is:
            //   <h3><a href="/slug/">Post Title</a></h3>  (title link IS inside heading)
            mainContent.querySelectorAll('h2 > a[href], h3 > a[href], h4 > a[href]').forEach(titleAnchor => {
                if (titleAnchor.closest('nav, header, footer, .menu, [role="navigation"]')) return;
                const href = titleAnchor.href || '';
                const title = (titleAnchor.innerText || titleAnchor.textContent || '').trim();
                
                // Snippet hunt: look for descriptive text in sibling elements
                let snippet = '';
                const parent = titleAnchor.parentElement; // the heading h2/h3/h4
                const container = parent.parentElement;   // the wrapper div/article
                if (container) {
                    const texts = Array.from(container.querySelectorAll('p, div, span, .excerpt, .summary, .description'))
                        .map(el => (el.innerText || el.textContent || '').trim())
                        .filter(t => t.length > 20 && !t.includes(title));
                    snippet = texts.join(' | ');
                }
                
                if (title.length > 10) addResult(href, title, null, snippet);
            });

            // ── PASS 1b: Heading + nearby CTA pattern ────────────────────────
            // Handles pages like trigya.co/case-studies/ where each card is:
            //   <h3>Robert Griffin</h3>  ← plain text heading, NO <a> inside
            //   <a href="/robert-griffin/">Read More</a>  ← CTA link nearby
            // Strategy: find every standalone h3/h4 (not wrapping an <a>), then
            // look for the nearest "Read More" link within the same tight container.
            if (results.length === 0) {
                mainContent.querySelectorAll('h3, h4').forEach(heading => {
                    // h2 is too likely to be a page/section title — only h3/h4 are card titles
                    if (heading.closest('nav, header, footer, .menu, [role="navigation"]')) return;
                    // Skip headings that already contain an <a> (handled by Pass 1)
                    if (heading.querySelector('a')) return;

                    const title = (heading.innerText || heading.textContent || '').trim();
                    if (title.length < 3 || title.length > 150) return;

                    // Only search the IMMEDIATE parent container — not body/grandparent.
                    // This prevents a section h2 from stealing a Read More link from a
                    // card that is several siblings away.
                    let ctaLink = null;
                    const parent = heading.parentElement;
                    if (!parent) return;

                    // Reject if the parent is too large (body, main, section with many children)
                    // or is a structural element — card containers are always divs/li/figure etc.
                    const parentTag = parent.tagName.toLowerCase();
                    if (parentTag === 'body' || parentTag === 'main' || parentTag === 'html') return;
                    const directChildCount = parent.children.length;
                    if (directChildCount > 10) return;

                    const anchors = parent.querySelectorAll('a[href]');
                    for (const a of anchors) {
                        const txt = (a.innerText || a.textContent || '').trim().toLowerCase();
                        if (txt.includes('read more') || txt.includes('continue reading') ||
                            txt.includes('learn more') || txt.includes('view more')) {
                            ctaLink = a;
                            break;
                        }
                    }

                    if (ctaLink) {
                        // Snippet hunt
                        const allText = Array.from(parent.querySelectorAll('p, div, span'))
                            .map(el => (el.innerText || el.textContent || '').trim())
                            .filter(t => t.length > 15 && !t.includes(title))
                            .join(' | ');
                        addResult(ctaLink.href, title, null, allText);
                    }
                });
            }

            // ── PASS 2: Card container scraper ───────────────────────────────
            // Handles sites that wrap each post in article / .card / .post-* etc.
            if (results.length === 0) {
                const cards = mainContent.querySelectorAll(
                    'article, .card, [class*="post-item" i], [class*="blog-item" i], ' +
                    '[class*="post-card" i], [class*="blog-card" i], ' +
                    '[class*="wd-" i], .woodmart-info-box, ' +
                    '.elementor-widget-container, .elementor-column, .elementor-image-box-wrapper, ' +
                    '.elementor-post, .elementor-posts-container article, .e-con, ' +
                    '.wp-block-column, .service-card, .service-item, .listing-item, ' +
                    '.zpimage-anchor, .zpbutton-wrapper, .zpcol-content, .zpsuccess-story'
                );
                cards.forEach(card => {
                    if (card.closest('nav, header, footer')) return;
                    const links = card.querySelectorAll('a[href]');
                    let bestLink = null;
                    let bestTitle = '';

                    // Prefer "Read More / Continue reading" CTA — its href IS the article URL
                    for (const a of links) {
                        const txt = (a.innerText || a.textContent || '').trim().toLowerCase();
                        if (txt.includes('read more') || txt.includes('continue reading') || txt.includes('learn more')) {
                            bestLink = a;
                            break;
                        }
                    }
                    // Otherwise use first link with a real title
                    if (!bestLink) {
                        for (const a of links) {
                            const txt = (a.innerText || a.textContent || '').trim();
                            if (txt.length > 10 && !DATE_RE.test(txt) && !GENERIC_SET.has(txt.toLowerCase())) {
                                bestLink = a;
                                bestTitle = txt;
                                break;
                            }
                        }
                    }

                    // Pull title from the card heading if we don't have one yet
                    if (!bestTitle) {
                        const heading = card.querySelector('h1,h2,h3,h4,h5,h6,[class*="title" i], [class*="heading" i]');
                        bestTitle = heading ? (heading.innerText || heading.textContent || '').trim() : '';
                    }

                    // Fallback to the listing URL itself if no link is found in the card (single-page services)
                    const finalLink = bestLink ? bestLink.href : listingUrl;

                    // Card Snippet: Harvest all descriptive text from the container
                    const allText = Array.from(card.querySelectorAll('p, div, span, .excerpt, .summary, .description, .content'))
                        .map(el => (el.innerText || el.textContent || '').trim())
                        .filter(t => t.length > 15 && !t.includes(bestTitle) && !GENERIC_SET.has(t.toLowerCase()))
                        .join(' | ');

                    if (bestTitle.length > 3) {
                        addResult(finalLink, bestTitle, null, allText);
                    }
                });
            }

            // ── PASS 3: Strict fallback — only accept links that look like articles ──
            // Triggered only when passes 1 & 2 both find nothing.
            // Unlike the old fallback, this one enforces that the URL must:
            //   a) match a known content keyword, OR
            //   b) be a slug-style URL (no known service/page patterns) with a
            //      heading sibling or long anchor text.
            if (results.length === 0) {
                mainContent.querySelectorAll('a[href]').forEach(a => {
                    if (a.closest('nav, header, footer, .menu, [role="navigation"]')) return;
                    const href = a.href || '';
                    if (!href.startsWith('http') || !href.includes(baseDomain)) return;
                    if (isBadUrl(href)) return;
                    const norm = href.replace(/\/$/, '');
                    if (norm === normListing || seen.has(norm)) return;

                    const txt = (a.innerText || a.textContent || '').trim();
                    const lowerTxt = txt.toLowerCase();

                    // Must have real text AND either a known content URL pattern
                    // or a heading nearby (indicates it's a genuine article link)
                    const hasContentUrl = catByUrl(href) !== null;
                    const nearHeading = !!a.closest('h1,h2,h3,h4,h5,h6') ||
                                        !!a.querySelector('h1,h2,h3,h4,h5,h6');
                    const isCtaLink = GENERIC_SET.has(lowerTxt);  // "continue reading" etc.

                    if ((txt.length > 15 || isCtaLink) && (hasContentUrl || nearHeading || isCtaLink)) {
                        // For CTA links without titles, look for sibling heading
                        let title = isCtaLink ? '' : txt;
                        if (!title) {
                            const parent = a.parentElement;
                            const sib = parent && parent.querySelector('h1,h2,h3,h4,h5,h6');
                            title = sib ? (sib.innerText || sib.textContent || '').trim() : txt;
                        }
                        seen.add(norm);
                        results.push({
                            title: (title || txt).split('\n')[0].trim(),
                            link: href,
                            detectedCategory: catByUrl(href) || pageDefaultCat || 'case_studies'
                        });
                    }
                });
            }

            return results;
        }
    """, {
        "baseDomain": base_domain,
        "listingUrl": listing_url,
        "pageDefaultCat": page_default_cat,
        "strictPathFilter": strict_path_filter,
        "BLOG_URL_KW": BLOG_URL_KW,
        "CASE_URL_KW": CASE_URL_KW,
        "STORY_URL_KW": STORY_URL_KW,
        "BLOG_TEXT_KW": BLOG_TEXT_KW,
        "CASE_TEXT_KW": CASE_TEXT_KW,
        "STORY_TEXT_KW": STORY_TEXT_KW,
        "BAD_URL_PATTERNS": BAD_URL_PATTERNS,
        "GENERIC_LINK_TEXT": list(GENERIC_LINK_TEXT),
        "DATE_REGEX_SRC": DATE_REGEX.pattern,
    })


def _page_default_category(page) -> str | None:
    """
    Infer the category of a listing page from its h1 / page-title element,
    then from the URL. URL-based fallback is critical for sites like trigya.co
    where the heading text ('Real Results, Proven Success') contains no keyword.
    """
    try:
        heading = page.evaluate("""
            () => {
                const el = document.querySelector(
                    'h1, .page-title, .hero-title, .section-heading, .page-heading'
                );
                return el ? (el.innerText || el.textContent || '').trim() : '';
            }
        """)
        if heading:
            cat = _categorise_by_text(heading)
            if cat:
                return cat
    except Exception:
        pass
    # Always fall back to URL-based detection (reliable for /blog/, /case-studies/, etc.)
    return _categorise_by_url(page.url)


def extract_all_page_content(agent, url: str) -> dict:
    """
    Universal content extractor — reads EVERY meaningful element on any page.
    Works on any website regardless of structure. Never returns null/empty.

    Extracts:
      - h1/h2/h3/h4 headings with their following paragraphs
      - All <p> paragraphs longer than 40 chars
      - All <li> list items longer than 20 chars
      - <blockquote> testimonials/quotes
      - <table> structured data
      - <strong>/<b> key terms
      - meta title + description
      - contact info (phone, email, address)

    Returns structured dict — never null values
    """
    result = {
        "url": url,
        "title": None,
        "meta_description": None,
        "h1": [],
        "sections": [],       # [{heading, paragraphs, lists}]
        "paragraphs": [],     # standalone paragraphs
        "lists": [],          # standalone list items
        "quotes": [],         # blockquotes / testimonials
        "contact": {          # always present, filled if found
            "phone": None,
            "email": None,
            "address": None
        },
        "key_terms": [],      # strong/b tags
        "raw_text": None      # full body text as last resort
    }

    try:
        # ── Meta ──────────────────────────────────────────────────────────────
        try:
            result["title"] = agent.page.title().strip() or None
        except: pass

        try:
            meta = agent.page.locator("meta[name='description']").get_attribute("content", timeout=3000)
            if meta and len(meta) > 20:
                result["meta_description"] = meta.strip()
        except: pass

        # ── H1 ────────────────────────────────────────────────────────────────
        try:
            h1s = agent.page.locator("h1").all()
            for h in h1s[:3]:
                try:
                    t = h.inner_text().strip()
                    if t and len(t) > 3:
                        result["h1"].append(t)
                except: pass
        except: pass

        # ── Sections: h2/h3/h4 + their following content ──────────────────────
        try:
            headings = agent.page.locator("h2, h3, h4").all()
            for heading in headings[:40]:
                try:
                    h_text = heading.inner_text().strip()
                    if not h_text or len(h_text) < 4 or len(h_text) > 150:
                        continue
                    # Skip pure nav/UI headings
                    skip = ['cookie', 'privacy', 'terms', 'sign in', 'log in',
                            'sign up', 'register', 'subscribe', 'newsletter',
                            'follow us', 'share', 'related', 'tags', 'categories']
                    if any(s in h_text.lower() for s in skip):
                        continue

                    section = {"heading": h_text, "paragraphs": [], "lists": []}

                    # Following sibling paragraphs
                    try:
                        sibs = heading.locator('~ p').all()
                        for sib in sibs[:4]:
                            try:
                                t = sib.inner_text().strip()
                                if t and len(t) > 30:
                                    section["paragraphs"].append(t)
                            except: pass
                    except: pass

                    # Following sibling lists
                    try:
                        ul_sibs = heading.locator('~ ul li, ~ ol li').all()
                        for li in ul_sibs[:8]:
                            try:
                                t = li.inner_text().strip()
                                if t and len(t) > 15:
                                    section["lists"].append(t)
                            except: pass
                    except: pass

                    if section["paragraphs"] or section["lists"] or len(h_text.split()) > 3:
                        result["sections"].append(section)
                except: pass
        except: pass

        # ── Standalone paragraphs ──────────────────────────────────────────────
        try:
            paras = agent.page.locator("main p, article p, .content p, section p, p").all()
            seen_p = set()
            for p in paras[:60]:
                try:
                    t = p.inner_text().strip()
                    if t and len(t) > 40 and t not in seen_p:
                        seen_p.add(t)
                        result["paragraphs"].append(t)
                except: pass
        except: pass

        # ── List items ────────────────────────────────────────────────────────
        try:
            lis = agent.page.locator("main li, article li, section li, ul li").all()
            seen_li = set()
            for li in lis[:50]:
                try:
                    t = li.inner_text().strip()
                    if t and len(t) > 20 and t not in seen_li:
                        seen_li.add(t)
                        result["lists"].append(t)
                except: pass
        except: pass

        # ── Blockquotes / testimonials ─────────────────────────────────────────
        try:
            bqs = agent.page.locator("blockquote, .testimonial, .quote, [class*='testimonial'], [class*='review']").all()
            for bq in bqs[:10]:
                try:
                    t = bq.inner_text().strip()
                    if t and len(t) > 20:
                        result["quotes"].append(t[:500])
                except: pass
        except: pass

        # ── Contact info ──────────────────────────────────────────────────────
        try:
            body_text = agent.page.locator("body").inner_text()

            import re as _re
            # Phone
            phone_match = _re.search(
                r'(\+?[\d\s\-\(\)]{7,15})', body_text
            )
            if phone_match:
                result["contact"]["phone"] = phone_match.group(1).strip()

            # Email
            email_match = _re.search(
                r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', body_text
            )
            if email_match:
                result["contact"]["email"] = email_match.group(0)

            # Address (look for street/road/avenue patterns)
            addr_match = _re.search(
                r'\d+\s+[A-Z][a-zA-Z\s]+(Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Way|Place|Pl)[,\s]+[A-Za-z\s,]+\d{4,}',
                body_text
            )
            if addr_match:
                result["contact"]["address"] = addr_match.group(0).strip()

            # Key terms (strong/b tags)
            strongs = agent.page.locator("strong, b").all()
            seen_kw = set()
            for s in strongs[:20]:
                try:
                    t = s.inner_text().strip()
                    if t and 3 < len(t) < 60 and t.lower() not in seen_kw:
                        seen_kw.add(t.lower())
                        result["key_terms"].append(t)
                except: pass

        except: pass

        # ── Raw text fallback (always populated) ──────────────────────────────
        try:
            raw = agent.page.locator("body").inner_text().strip()
            # Collapse whitespace
            import re as _re2
            raw = _re2.sub(r'\n{3,}', '\n\n', raw)
            raw = _re2.sub(r'[ \t]{2,}', ' ', raw)
            result["raw_text"] = raw[:3000]
        except: pass

    except Exception as e:
        print(f"[*] extract_all_page_content error on {url}: {e}", file=sys.stderr)

    return result


def universal_site_crawler(agent, base_url: str, nav_links: list = None) -> list:
    """
    Universal crawler — visits ALL internal pages of any website and
    extracts structured content from each. Never returns empty.

    Pages visited (in priority order):
      1. Real nav links discovered from the site itself (highest priority)
      2. Hardcoded common paths as fallback (about, services, team, etc.)

    Returns list of general_content items built from all extracted content.
    """
    from urllib.parse import urljoin, urlparse

    # 404 / error phrases to filter out — we never store these as real content
    JUNK_PHRASES = [
        "page could not be found", "404", "page not found", "not found",
        "error 404", "doesn't exist", "does not exist", "nothing here",
        "oops", "went wrong", "no longer available"
    ]

    def is_junk_content(text: str) -> bool:
        t = text.lower().strip()
        return any(p in t for p in JUNK_PHRASES) or len(t) < 30

    HARDCODED_PATHS = [
        # About
        '/about', '/about-us', '/about-us/', '/our-story',
        '/company', '/who-we-are', '/our-team',
        # Services
        '/services', '/services/', '/what-we-do',
        '/solutions', '/our-services', '/offerings',
        '/expertise', '/capabilities', '/specialties',
        # Work/Portfolio
        '/portfolio', '/work', '/projects', '/our-work',
        '/case-studies', '/success-stories',
        # Other
        '/team', '/contact',
    ]

    results = []
    visited = set()
    visited.add(base_url.rstrip('/'))
    base_domain = urlparse(base_url).netloc.replace('www.', '')

    # Skip URLs that are not real content pages
    SKIP_KEYWORDS = [
        '/cart', '/checkout', '/login', '/signup', '/register',
        '/privacy', '/cookie', '/terms', '/career', '/pricing',
        'facebook.com', 'instagram.com', 'twitter.com', 'youtube.com',
        'linkedin.com', 'tel:', 'mailto:', '#'
    ]

    def should_skip(url: str) -> bool:
        return any(k in url.lower() for k in SKIP_KEYWORDS)

    def page_to_content_items(page_data: dict, page_url: str) -> list:
        """Converts extract_all_page_content output into general_content items."""
        items = []

        # One item per section (heading + content)
        for section in page_data.get("sections", []):
            heading = section.get("heading", "")
            paras   = section.get("paragraphs", [])
            lists   = section.get("lists", [])
            if not heading or is_junk_content(heading):
                continue
            body_parts = paras + lists
            content = f"{heading}. {' '.join(body_parts[:3])}" if body_parts else heading
            if len(content) > 20 and not is_junk_content(content):
                items.append({
                    "title": heading,
                    "link": page_url,
                    "content": minify_text(content[:800]),
                    "detected_type": "general_content"
                })

        # If no sections found, use standalone paragraphs
        if not items:
            paras = page_data.get("paragraphs", [])
            if paras:
                combined = " ".join(paras[:3])
                if not is_junk_content(combined):
                    page_title = page_data.get("title") or urlparse(page_url).path.strip('/').replace('-', ' ').title() or "Page Content"
                    if not is_junk_content(page_title):
                        items.append({
                            "title": page_title,
                            "link": page_url,
                            "content": minify_text(combined[:800]),
                            "detected_type": "general_content"
                        })

        # If still nothing, use raw_text snippet
        if not items and page_data.get("raw_text"):
            raw = page_data["raw_text"][:400].strip()
            if len(raw) > 50 and not is_junk_content(raw):
                page_title = page_data.get("title") or "Page Content"
                items.append({
                    "title": page_title,
                    "link": page_url,
                    "content": minify_text(raw),
                    "detected_type": "general_content"
                })

        return items

    def visit_and_extract(target_url: str, label: str = "") -> int:
        """Visits a URL and adds extracted items to results. Returns count added."""
        nonlocal results
        if target_url.rstrip('/') in visited or should_skip(target_url):
            return 0
        try:
            resp = agent._safe_goto(target_url, wait_until="domcontentloaded", timeout=20000)
            if not resp or resp.status >= 400:
                return 0
            agent.page.wait_for_timeout(800)
            current = agent.page.url
            if base_domain not in current:
                return 0
            visited.add(target_url.rstrip('/'))
            visited.add(current.rstrip('/'))
            page_data  = extract_all_page_content(agent, current)
            page_items = page_to_content_items(page_data, current)
            if page_items:
                print(f"[+] {label or target_url}: {len(page_items)} items extracted.", file=sys.stderr)
                results.extend(page_items)
            else:
                print(f"[*] {label or target_url}: No useful content found.", file=sys.stderr)
            return len(page_items)
        except Exception as e:
            print(f"[*] Universal crawler: Could not load {target_url}: {e}", file=sys.stderr)
            return 0

    # ── Step 1: Extract from homepage (already loaded) ─────────────────────
    print(f"[*] Universal crawler: Extracting homepage content...", file=sys.stderr)
    homepage_data = extract_all_page_content(agent, base_url)
    homepage_items = page_to_content_items(homepage_data, base_url)
    results.extend(homepage_items)
    print(f"[+] Homepage: {len(homepage_items)} content items extracted.", file=sys.stderr)

    # ── Step 2: Visit REAL nav links from the site first ──────────────────
    # These are the actual pages the site has, discovered from the navigation.
    # This is the most reliable source of content.
    if nav_links:
        # nav_links is list of {text, href} dicts from _collect_all_nav_links
        real_urls = [item["href"] for item in nav_links if isinstance(item, dict) and item.get("href")] if nav_links and isinstance(nav_links[0], dict) else nav_links
        print(f"[*] Universal crawler: Visiting {len(real_urls)} real nav links...", file=sys.stderr)
        for nav_url in real_urls:
            if len(results) >= 20:
                break
            label = nav_url.rstrip('/').split('/')[-1] or 'nav-page'
            visit_and_extract(nav_url, label)

    # ── Step 3: Try hardcoded fallback paths (catches sites with standard URL structures) ──
    for path in HARDCODED_PATHS:
        if len(results) >= 20:
            break
        target_url = base_url.rstrip('/') + path
        visit_and_extract(target_url, path)

    # ── Step 4: Go back to homepage ────────────────────────────────────────
    try:
        agent._safe_goto(base_url, timeout=10000)
    except: pass

    print(f"[+] Universal crawler complete: {len(results)} total content items from {base_url}", file=sys.stderr)
    return results


def extract_homepage_services(agent, base_url: str) -> list:
    """
    Extracts service cards from a homepage or services page.
    Designed for local/trade businesses (like shrink-wrap.co.nz) that have
    rich service content on their homepage but no blog/case study section.

    Strategy:
    1. Read current page (homepage already loaded) for service cards
    2. Also check common service page URLs (/services, /what-we-do, etc.)
    3. Look for heading+description card patterns (h2/h3/h4 + p)
    4. Follow service links (READ MORE / Learn More) to get deeper content
    5. Return list of general_content items with title + description + link

    Returns list of dicts: [{title, link, content, detected_type}]
    """
    results = []
    seen_links = set()
    seen_titles = set()

    # Card container selectors — covers most business site grid layouts
    CARD_SELECTORS = [
        ".services .card", ".service-card", ".service-item",
        ".services-grid > div", ".services-list > li",
        "[class*='service'] h2", "[class*='service'] h3",
        ".solutions .card", ".solution-item",
        ".what-we-do .item", ".offerings .item",
        "article", ".card", ".feature-item",
        "section div[class*='col']", "section div[class*='block']",
    ]

    # Common service page URLs to check after homepage
    SERVICE_PAGE_PATHS = ['/services', '/services/', '/what-we-do', '/solutions', '/our-services', '/our-work']

    try:
        import requests as _req
        # --- Step 0: Pre-filter service paths with fast HEAD requests ---
        # This avoids wasting a full 3-retry Playwright navigation on 404 paths.
        urls_to_scan = [base_url]
        for path in SERVICE_PAGE_PATHS:
            full_url = base_url.rstrip('/') + path
            if full_url in urls_to_scan:
                continue
            try:
                r = _req.head(full_url, timeout=4, allow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code < 400:
                    urls_to_scan.append(full_url)
            except:
                pass  # can't reach — skip

        for scan_url in urls_to_scan:
            try:
                # If it's a sub-page, navigate to it
                if scan_url != base_url:
                    print(f"[*] Checking potential services page: {scan_url}", file=sys.stderr)
                    try:
                        resp = agent._safe_goto(scan_url, timeout=8000)
                        if not resp or resp.status >= 400:
                            continue
                        agent.page.wait_for_timeout(1000)  # give JS time to render
                    except: continue

                # --- Step 1a: Direct h2/h3/h4 + following p extraction (for flat layouts like hitwrapnz.com) ---
                headings = agent.page.locator('h2, h3, h4').all()
                for heading in headings:
                    try:
                        title = heading.inner_text().strip()
                        if not title or len(title) < 5 or len(title) > 100: continue
                        
                        # Skip nav/footer items and generics
                        skip_words = ['home', 'contact', 'about us', 'menu', 'login', 'sign up', 'privacy', 'terms', 'faq', 'blog', 'case studies']
                        if any(sw in title.lower() for sw in skip_words):
                            continue
                            
                        t_norm = title.lower()
                        if t_norm in seen_titles: continue

                        # Try to get the paragraph that follows
                        desc = None
                        try:
                            # Use ~ p to find following sibling paragraph
                            p_sib = heading.locator('~ p').first
                            if p_sib.count() > 0:
                                desc = p_sib.inner_text().strip()
                                if desc and len(desc) < 15: desc = None
                        except: pass

                        if desc or (len(title.split()) > 3): # If no desc, title must be descriptive
                            seen_titles.add(t_norm)
                            results.append({
                                "title": title,
                                "link": scan_url,
                                "content": f"{title}. {desc}" if desc else title,
                                "detected_type": "general_content"
                            })
                    except: continue

                # --- Step 1b: Extract from standard card containers ---
                for selector in CARD_SELECTORS:
                    try:
                        cards = agent.page.locator(selector).all()
                        if not cards: continue
                        for card in cards[:15]:
                            try:
                                title = None
                                for htag in ['h2', 'h3', 'h4', 'strong']:
                                    try:
                                        t = card.locator(htag).first.inner_text().strip()
                                        if t and 4 < len(t) < 120:
                                            title = t
                                            break
                                    except: continue

                                if not title: continue
                                t_norm = title.lower()
                                if t_norm in seen_titles: continue

                                skip_words = ['home', 'contact', 'about us', 'menu', 'login', 'sign up', 'privacy', 'terms', 'faq']
                                if any(sw in t_norm for sw in skip_words): continue

                                desc = None
                                try:
                                    desc = card.locator('p').first.inner_text().strip()
                                    if desc and len(desc) < 10: desc = None
                                except: pass

                                link = None
                                try:
                                    anchor = card.locator('a').first
                                    href = anchor.get_attribute('href')
                                    if href:
                                        from urllib.parse import urljoin
                                        link = urljoin(base_url, href)
                                        # Skip external and policy
                                        if not link.startswith(base_url.rstrip('/').split('/')[0] + '//' + base_url.split('/')[2]):
                                            link = None
                                        if link and any(s in link.lower() for s in ['privacy', 'terms', 'cookie', 'login']):
                                            link = None
                                except: pass

                                if link and link.rstrip('/') in seen_links: continue

                                seen_titles.add(t_norm)
                                content = f"{title}. {desc}" if desc else title
                                results.append({
                                    "title": title,
                                    "link": link or scan_url,
                                    "content": content,
                                    "detected_type": "general_content"
                                })
                                if link: seen_links.add(link.rstrip('/'))
                            except: continue
                    except: continue

                if len(results) >= 10: break # found enough — stop early

            except Exception: continue

        # --- Step 2: Follow links for deeper content (capped at 6 to balance speed vs completeness) ---
        if results:
            print(f"[+] Service discovery: Found {len(results)} items. Fetching deep content for top 6 items...", file=sys.stderr)
            for item in results[:6]:
                link = item.get("link", "")
                if not link or link == base_url or any(path in link for path in SERVICE_PAGE_PATHS):
                    continue # already scanned the page or it's just the root
                try:
                    agent._safe_goto(link, timeout=10000)
                    agent.page.wait_for_timeout(800)
                    deep_text = None
                    for sel in ["main", "article", ".content", ".page-content", "#content"]:
                        try:
                            t = agent.page.locator(sel).first.inner_text().strip()
                            if t and len(t) > 100:
                                deep_text = t[:1000]
                                break
                        except: continue
                    if deep_text:
                        item["content"] = minify_text(f"{item['title']}. {deep_text}")
                except: continue

            # Back to homepage if needed (for next steps in agent)
            try: agent._safe_goto(base_url, timeout=10000)
            except: pass

    except Exception as e:
        print(f"[*] extract_homepage_services error: {e}", file=sys.stderr)

    return results


def extract_from_external_website(agent, url: str) -> dict:
    """
    3-Step extraction from a company's official website:

    Step 1 — Fully expand navbar (CSS hover + JS click on dropdowns/More menus)
              then collect ALL nav/header/footer links.
    Step 2 — For every relevant listing page: open it, reveal lazy-loaded cards,
              harvest article links with title + category.
    Step 3 — Navigate to each article and extract its full text content.
    """
    results = {"blogs": [], "case_studies": [], "customer_stories": [], "general_content": []}
    MAX_ARTICLES_PER_CAT = 6  # reduced to speed up discovery
    MAX_LISTING_PAGES = 12     # reduced to speed up discovery

    try:
        # ── Step 1: Load homepage, expand nav, collect links ─────────────────
        print(f"[*] Step 1: Loading site and expanding nav: {url}", file=sys.stderr)
        agent._safe_goto(url, wait_until="domcontentloaded", timeout=25000)
        agent.page.wait_for_timeout(2000)

        parsed = urlparse(url)
        base_domain = parsed.netloc.replace("www.", "")

        _expand_nav_fully(agent.page)

        nav_links = _collect_all_nav_links(agent.page, base_domain)
        print(f"[*]   Collected {len(nav_links)} nav links total.", file=sys.stderr)

        listing_targets = _build_listing_targets(nav_links, url)
        print(f"[*]   {len(listing_targets)} listing targets identified.", file=sys.stderr)

        # ── Step 2: Visit each listing page, collect article links ────────────
        article_queue: dict[str, list] = {"blogs": [], "case_studies": [], "customer_stories": [], "general_content": []}
        # Track seen links PER CATEGORY so a blog URL found as a cross-link on
        # the case-studies page doesn't block it from being queued from the blog listing
        seen_links: dict[str, set] = {"blogs": set(), "case_studies": set(), "customer_stories": set(), "general_content": set()}

        for target in listing_targets[:MAX_LISTING_PAGES]:
            print(f"[*] Step 2: Scanning listing page [{target['type']}]: {target['url']}",
                  file=sys.stderr)

            # Use the target's own type as the default category for articles found on it.
            # This is the most reliable signal — a page identified as 'blogs' listing
            # will contain blog articles, even if their URLs are slug-only (no /blog/ prefix).
            # For 'generic' targets we still try to infer from the page heading/URL.
            if target["type"] != "generic":
                page_default_cat = target["type"]
            else:
                page_default_cat = _page_default_category(agent.page) \
                    if target["url"] == url else None

            articles = _collect_articles_from_listing(
                agent, target["url"], base_domain, page_default_cat
            )

            # For generic targets: re-read category from the loaded page
            if target["type"] == "generic" and not page_default_cat:
                page_default_cat = _page_default_category(agent.page)

            # Re-apply page default to articles that have no category yet
            for art in articles:
                if not art.get("detectedCategory") and page_default_cat:
                    art["detectedCategory"] = page_default_cat

            print(f"[*]   Found {len(articles)} candidate article links.", file=sys.stderr)

            # ── Direct content extraction for pages with no sub-links ────────────
            # Service pages, About pages, etc. are self-contained — they don't contain
            # links to child articles. When 0 articles found, grab the page content directly.
            if len(articles) == 0 and target["type"] in ("general_content", "generic"):
                try:
                    page_data = extract_all_page_content(agent, target["url"])
                    page_title = page_data.get("title") or target["url"].rstrip("/").split("/")[-1].replace("-", " ").title()
                    
                    # Build content from sections or paragraphs
                    content_parts = []
                    for section in page_data.get("sections", [])[:5]:
                        heading = section.get("heading", "")
                        paras   = section.get("paragraphs", [])
                        if heading and paras:
                            content_parts.append(f"{heading}: {' '.join(paras[:2])}")
                        elif heading:
                            content_parts.append(heading)
                    
                    if not content_parts:
                        content_parts = page_data.get("paragraphs", [])[:4]
                    
                    combined = " | ".join(content_parts)
                    
                    JUNK_PHRASES = ["page could not be found", "404", "page not found", "oops", "went wrong"]
                    if combined and len(combined) > 40 and not any(p in combined.lower() for p in JUNK_PHRASES):
                        article_queue["general_content"].append({
                            "title": page_title,
                            "link": target["url"],
                            "content": combined[:800],
                            "detected_type": "general_content"
                        })
                        print(f"[+]   Direct content extracted from {target['url']} ({len(combined)} chars)", file=sys.stderr)
                except Exception as ce:
                    print(f"[*]   Could not extract direct content from {target['url']}: {ce}", file=sys.stderr)

            for art in articles:
                lk = art["link"].rstrip("/")

                # Determine final bucket first, then check per-category dedup
                detected = art.get("detectedCategory")
                if detected in article_queue:
                    cat = detected
                elif target["type"] != "generic" and target["type"] in article_queue:
                    cat = target["type"]
                else:
                    cat = "case_studies"

                # Deduplicate within the bucket only — not globally across categories
                if lk in seen_links[cat]:
                    continue
                seen_links[cat].add(lk)

                if len(article_queue[cat]) < MAX_ARTICLES_PER_CAT:
                    article_queue[cat].append(art)
                    print(f"[*]     → queued [{cat}]: {art['link']}", file=sys.stderr)

            # Early exit only when all buckets have ENOUGH articles
            if all(len(v) >= MAX_ARTICLES_PER_CAT for v in article_queue.values()):
                print("[*]   All buckets full, stopping listing scan.", file=sys.stderr)
                break

        # ── Step 3: Extract full content from each article ────────────────────
        for cat, arts in article_queue.items():
            for art in arts:
                # Skip re-fetch if content was already extracted directly (e.g. service pages)
                if art.get("content"):
                    results[cat].append({
                        "title": art["title"],
                        "link": art["link"],
                        "content": art["content"],
                        "detected_type": cat
                    })
                    continue
                print(f"[*] Step 3: Extracting [{cat}]: {art['link']}", file=sys.stderr)
                content = extract_page_content(agent, art["link"])
                results[cat].append({
                    "title": art["title"],
                    "link": art["link"],
                    "content": content or "Content extraction failed.",
                    "detected_type": cat
                })

    except Exception as e:
        print(f"[*] External site error: {e}", file=sys.stderr)

    return results

def extract_from_manual_links(agent, blog_url: str | None, case_study_url: str | None, customer_story_url: str | None = None) -> dict:
    """
    Scrapes blogs, case studies, and customer stories from specific URLs.
    """
    results = {"blogs": [], "case_studies": [], "customer_stories": []}
    MAX_ARTICLES_PER_CAT = 5
    
    listing_targets = []
    if blog_url:
        listing_targets.append({"url": blog_url, "type": "blogs"})
    if case_study_url:
        listing_targets.append({"url": case_study_url, "type": "case_studies"})
    if customer_story_url:
        listing_targets.append({"url": customer_story_url, "type": "customer_stories"})
        
    if not listing_targets:
        return results

    try:
        # Get base_domain for filtering
        first_url = blog_url or case_study_url
        parsed = urlparse(first_url)
        base_domain = parsed.netloc.replace("www.", "")

        article_queue: dict[str, list] = {"blogs": [], "case_studies": [], "customer_stories": []}
        seen_links: set[str] = set()

        for target in listing_targets:
            print(f"[*] Scanning provided listing page [{target['type']}]: {target['url']}", file=sys.stderr)
            
            # Use strict_path_filter=False for manual links because we trust the user's provided URL
            articles = _collect_articles_from_listing(
                agent, target["url"], base_domain, target["type"], strict_path_filter=False
            )

            print(f"[*]   Found {len(articles)} candidate article links.", file=sys.stderr)

            for art in articles:
                lk = art["link"].rstrip("/")
                if lk in seen_links:
                    continue
                seen_links.add(lk)

                # Use the detected category if available, else fallback to the target type
                cat = art.get("detectedCategory") or target["type"]
                if cat not in article_queue: 
                    cat = "case_studies" # safe fallback

                if len(article_queue[cat]) < MAX_ARTICLES_PER_CAT:
                    article_queue[cat].append(art)
                    print(f"[*]     → queued [{cat}]: {art['link']}", file=sys.stderr)

        # Step 3: Extract content from each article
        for cat, arts in article_queue.items():
            for art in arts:
                print(f"[*] Extracting [{cat}]: {art['link']}", file=sys.stderr)
                content = extract_page_content(agent, art["link"])
                results[cat].append({
                    "title": art["title"],
                    "link": art["link"],
                    "content": content or "Content extraction failed.",
                    "detected_type": cat
                })

    except Exception as e:
        print(f"[*] Manual links extraction error: {e}", file=sys.stderr)

    return results


def extract_social_links(agent) -> dict:
    """Find Instagram, Twitter, Facebook, and YouTube links on the partner's website."""
    social_links = {"instagram": None, "twitter": None, "facebook": None, "youtube": None}
    platforms = {
        "instagram": ["instagram.com"],
        "twitter": ["twitter.com", "x.com"],
        "facebook": ["facebook.com"],
        "youtube": ["youtube.com"]
    }
    
    try:
        # 1. Scroll to ensure footer/sidebars are rendered
        agent._scroll_to_bottom()
        agent.page.wait_for_timeout(1000)
        
        # 2. General anchor search
        anchors = agent.page.locator("a[href]").all()
        for a in anchors:
            try:
                href = a.get_attribute("href")
                if not href: continue
                for platform, keywords in platforms.items():
                    if social_links.get(platform): continue
                    if any(kw in href.lower() for kw in keywords):
                        # Filter out generic/corporate links and sharing intents
                        if not any(x in href.lower() for x in ["share", "intent", "sharer", "plugins", "zoho", "/p/"]):
                            social_links[platform] = href
            except Exception: continue
            
        # 3. Icon-based fallback (if text is missing)
        if not all(social_links.values()):
            icon_selectors = {
                "instagram": ["i.fa-instagram", ".instagram", "[class*='instagram' i]"],
                "twitter": ["i.fa-twitter", "i.fa-x-twitter", ".twitter", "[class*='twitter' i]", "[class*='x-twitter' i]"],
                "facebook": ["i.fa-facebook", ".facebook", "[class*='facebook' i]"],
                "youtube": ["i.fa-youtube", ".youtube", "[class*='youtube' i]"]
            }
            for platform, selectors in icon_selectors.items():
                if social_links.get(platform): continue
                for sel in selectors:
                    try:
                        icon = agent.page.locator(sel).first
                        if icon.count() > 0:
                            # Try to find parent anchor
                            parent = icon.locator("xpath=ancestor::a").first
                            if parent.count() > 0:
                                href = parent.get_attribute("href")
                                if href and any(kw in href.lower() for kw in platforms[platform]):
                                    social_links[platform] = agent._absolute_url(href)
                                    break
                    except Exception: continue
                    
    except Exception as e:
        print(f"[*] Warning: Error extracting social links: {e}", file=sys.stderr)
        
    return social_links


def scrape_social_platform(agent, url: str, platform: str) -> dict:
    """Best-effort scrape of a social media profile without login."""

    # ALL major social platforms block headless browsers causing ERR_ABORTED
    # This happens on deployed AppSail but not always on localhost because
    # localhost may have a real Chrome session — AppSail uses pure headless Chromium.
    # Skipping prevents 45s+ timeouts per platform per company.
    BLOCKED_PLATFORMS = {"youtube", "instagram", "twitter", "facebook"}
    if platform in BLOCKED_PLATFORMS:
        print(f"[*] Offloading {platform.capitalize()} to AI Deep Intelligence for unblockable extraction...", file=sys.stderr)
        return {"url": url, "bio": None, "posts": [], "error": "Handled by AI Discovery"}

    print(f"[*] Attempting best-effort scrape of {platform}: {url}", file=sys.stderr)
    data = {"url": url, "bio": None, "posts": [], "error": None}
    
    try:
        # Reduced timeout for social (if it doesn't load in 15s, it's likely blocked)
        agent._safe_goto(url, wait_until="domcontentloaded", timeout=15000)
        agent.page.wait_for_timeout(2000)
        
        if platform == "instagram":
            try:
                data["bio"] = agent.page.locator("meta[name='description']").get_attribute("content", timeout=5000)
            except:
                data["bio"] = agent._safe_text("header section")
            try:
                anchors = agent.page.locator("a[href*='/p/'] img").all()
                for img in anchors[:3]:
                    alt = img.get_attribute("alt", timeout=2000)
                    if alt: data["posts"].append({"content": alt})
            except: pass
                
        elif platform == "twitter":
            data["bio"] = agent._safe_text("[data-testid='UserDescription']") or agent.page.title()
            try:
                tweets = agent.page.locator("[data-testid='tweetText']").all()
                for t in tweets[:2]:
                    data["posts"].append({"content": t.inner_text()})
            except: pass
                
        elif platform == "facebook":
            data["bio"] = agent._safe_text("div:has-text('About') + div") or agent.page.title()
            try:
                posts = agent.page.locator("[data-ad-preview='message']").all()
                for p in posts[:2]:
                    data["posts"].append({"content": p.inner_text()})
            except: pass

        elif platform == "youtube":
            data["bio"] = agent._safe_text("#description-container") or agent.page.title()
            try:
                videos = agent.page.locator("#video-title").all()
                for v in videos[:2]:
                    data["posts"].append({"content": v.inner_text()})
            except: pass
                
    except Exception as e:
        data["error"] = str(e)
        print(f"[*] Social scrape skip for {platform}: {e}", file=sys.stderr)
        
    return data


# ------------------------------------------------------------------ #
# FALLBACK DATA SOURCE SCRAPERS
# Called when own-site content is zero or below threshold
# ------------------------------------------------------------------ #

def count_content_items(data: dict) -> int:
    """Returns total number of scraped content items across all 3 categories."""
    return (
        len(data.get("blogs", [])) +
        len(data.get("case_studies", [])) +
        len(data.get("customer_stories", []))
    )


def check_content_threshold(data: dict, threshold: int = 2) -> bool:
    """Returns True if content is BELOW threshold and fallback should be triggered."""
    return count_content_items(data) < threshold


def scrape_g2_reviews(company_name: str) -> dict:
    """
    Fetches public review signals from G2 for a company.
    Returns structured data for Customer Success dimension scoring.
    """
    import requests
    result = {
        "source": "G2",
        "found": False,
        "review_count": 0,
        "avg_rating": None,
        "snippets": [],
        "profile_url": None
    }
    try:
        slug = company_name.lower().replace(" ", "-").replace(".", "")
        url = f"https://www.g2.com/products/{slug}/reviews"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200 and "reviews" in resp.text.lower():
            result["found"] = True
            result["profile_url"] = url
            # Extract review count via simple pattern
            import re
            count_match = re.search(r'([\d,]+)\s+reviews?', resp.text, re.I)
            if count_match:
                result["review_count"] = int(count_match.group(1).replace(",", ""))
            rating_match = re.search(r'(\d\.\d)\s+out of\s+5', resp.text, re.I)
            if rating_match:
                result["avg_rating"] = float(rating_match.group(1))
            print(f"[+] G2 fallback: Found {result['review_count']} reviews for {company_name}", file=sys.stderr)
        else:
            print(f"[*] G2 fallback: No profile found for {company_name}", file=sys.stderr)
    except Exception as e:
        print(f"[*] G2 fallback error for {company_name}: {e}", file=sys.stderr)
    return result


def scrape_news_mentions(company_name: str) -> dict:
    """
    Searches Google News RSS for company mentions.
    Returns structured data for Market Authority dimension scoring.
    """
    import requests
    import re
    result = {
        "source": "Google News",
        "found": False,
        "mention_count": 0,
        "headlines": []
    }
    try:
        query = company_name.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            titles = re.findall(r'<title>(.*?)</title>', resp.text, re.DOTALL)
            # Skip first title — it's the feed title itself
            headlines = [t.strip() for t in titles[1:6] if t.strip() and company_name.split()[0].lower() in t.lower()]
            result["found"] = len(headlines) > 0
            result["mention_count"] = len(headlines)
            result["headlines"] = headlines
            print(f"[+] News fallback: Found {len(headlines)} mentions for {company_name}", file=sys.stderr)
        else:
            print(f"[*] News fallback: No results for {company_name}", file=sys.stderr)
    except Exception as e:
        print(f"[*] News fallback error for {company_name}: {e}", file=sys.stderr)
    return result


def scrape_linkedin_presence(linkedin_url: str) -> dict:
    """
    Does a lightweight check on a LinkedIn company page.
    Returns follower/presence signals for Market Authority scoring.
    """
    import requests
    import re
    result = {
        "source": "LinkedIn",
        "found": False,
        "followers": None,
        "description": None,
        "url": linkedin_url
    }
    if not linkedin_url:
        return result
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        resp = requests.get(linkedin_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            result["found"] = True
            follower_match = re.search(r'([\d,]+)\s+followers?', resp.text, re.I)
            if follower_match:
                result["followers"] = int(follower_match.group(1).replace(",", ""))
            desc_match = re.search(r'"description":"(.*?)"', resp.text)
            if desc_match:
                result["description"] = desc_match.group(1)[:300]
            print(f"[+] LinkedIn fallback: Found presence, followers={result['followers']}", file=sys.stderr)
        else:
            print(f"[*] LinkedIn fallback: Could not access {linkedin_url}", file=sys.stderr)
    except Exception as e:
        print(f"[*] LinkedIn fallback error: {e}", file=sys.stderr)
    return result


def scrape_search_presence(company_name: str, website_url: str) -> dict:
    """
    Uses DuckDuckGo to check how many results exist for the company.
    Proxy for search engine presence / Market Authority.
    """
    import requests
    import re
    result = {
        "source": "Search Engine",
        "found": False,
        "result_count_estimate": 0,
        "top_snippets": []
    }
    try:
        domain = website_url.replace("https://", "").replace("http://", "").split("/")[0] if website_url else company_name
        query = f'site:{domain} OR "{company_name}"'.replace(" ", "+")
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            snippets = re.findall(r'class="result__snippet">(.*?)</a>', resp.text, re.DOTALL)
            snippets = [re.sub(r'<.*?>', '', s).strip() for s in snippets[:5]]
            result["found"] = len(snippets) > 0
            result["result_count_estimate"] = len(snippets) * 10  # rough estimate
            result["top_snippets"] = snippets
            print(f"[+] Search fallback: Found ~{result['result_count_estimate']} results for {company_name}", file=sys.stderr)
    except Exception as e:
        print(f"[*] Search fallback error for {company_name}: {e}", file=sys.stderr)
    return result


# ------------------------------------------------------------------ #
# GENERIC OWN-SITE CONTENT SCRAPER
# For small/local businesses with no blogs — scrapes About/Services pages
# ------------------------------------------------------------------ #

GENERIC_CONTENT_PATHS = [
    '/about', '/about-us', '/about-us/', '/about/',
    '/services', '/services/', '/what-we-do', '/what-we-do/',
    '/products', '/products/', '/our-story', '/our-story/',
    '/company', '/company/', '/overview', '/who-we-are',
    '/our-work', '/solutions', '/expertise'
]

def scrape_own_site_generic_content(website_url: str) -> dict:
    """
    For small/local businesses that have no blogs or case studies,
    scrapes generic pages like About, Services, Products to extract
    at least an overview and basic business description.
    Returns structured content for overview population.
    """
    import requests
    import re
    result = {
        "source": "Own Website (Generic Pages)",
        "found": False,
        "overview": None,
        "services": [],
        "pages_found": []
    }
    if not website_url:
        return result

    base = website_url.rstrip("/")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html",
        "Accept-Language": "en-US,en;q=0.9"
    }

    collected_texts = []
    for path in GENERIC_CONTENT_PATHS:
        try:
            url = base + path
            resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 200:
                # Strip HTML tags
                text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                # Only keep meaningful content (not just nav/footer noise)
                if len(text) > 100:
                    collected_texts.append(text[:600])
                    result["pages_found"].append(path)
                    print(f"[+] Generic content found at {url}", file=sys.stderr)
                    if len(collected_texts) >= 3:
                        break  # 3 pages is enough
        except Exception:
            continue

    if collected_texts:
        result["found"] = True
        result["overview"] = " | ".join(collected_texts[:2])[:1000]
        result["services"] = collected_texts
        print(f"[+] Own-site generic scrape: {len(collected_texts)} pages found for {website_url}", file=sys.stderr)
    else:
        print(f"[*] Own-site generic scrape: No content found at generic paths for {website_url}", file=sys.stderr)

    return result


# ------------------------------------------------------------------ #
# GOOGLE MAPS / LOCAL BUSINESS SCRAPER
# For small local/trade businesses not on G2 or LinkedIn
# ------------------------------------------------------------------ #

def scrape_google_maps(company_name: str, website_url: str = "") -> dict:
    """
    Fetches local business signals from Google Maps search.
    Works well for small local businesses (trade suppliers, NZ/AU/UK companies)
    that are invisible on G2, LinkedIn, and news sources.
    Returns rating, review count, business category, address.
    """
    import requests
    import re
    result = {
        "source": "Google Maps",
        "found": False,
        "rating": None,
        "review_count": 0,
        "category": None,
        "address": None,
        "phone": None
    }
    try:
        # Extract country hint from URL TLD
        country_hint = ""
        if website_url:
            tld = website_url.split(".")[-1].split("/")[0].lower()
            tld_map = {"nz": "New Zealand", "au": "Australia", "uk": "United Kingdom",
                       "in": "India", "ca": "Canada", "sg": "Singapore"}
            country_hint = tld_map.get(tld, "")

        query = f"{company_name} {country_hint}".strip().replace(" ", "+")
        url = f"https://www.google.com/maps/search/{query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            text = resp.text
            # Rating pattern: 4.5 stars
            rating_match = re.search(r'"(\d\.\d)"\s*,\s*"(\d+(?:,\d+)?)\s*(?:reviews?|ratings?)"', text, re.I)
            if not rating_match:
                rating_match = re.search(r'(\d\.\d)\s*\((\d+(?:,\d+)?)\)', text)
            if rating_match:
                result["found"] = True
                result["rating"] = float(rating_match.group(1))
                result["review_count"] = int(rating_match.group(2).replace(",", ""))

            # Business category
            cat_match = re.search(r'"([A-Z][a-z]+(?: [A-Za-z]+){0,3})".*?"' + re.escape(company_name.split()[0]), text)
            if cat_match:
                result["category"] = cat_match.group(1)

            if result["found"]:
                print(f"[+] Google Maps: Found {company_name} — Rating {result['rating']} ({result['review_count']} reviews)", file=sys.stderr)
            else:
                print(f"[*] Google Maps: No structured data found for {company_name}", file=sys.stderr)
    except Exception as e:
        print(f"[*] Google Maps scrape error for {company_name}: {e}", file=sys.stderr)
    return result


# ------------------------------------------------------------------ #
# COUNTRY DETECTION FROM URL
# Routes fallback to the right sources based on company's TLD
# ------------------------------------------------------------------ #

def detect_country_from_url(url: str) -> str:
    """
    Detects company's country from URL TLD.
    Used to route fallback to local-appropriate sources.
    """
    if not url:
        return "global"
    tld = url.rstrip("/").split(".")[-1].split("/")[0].lower()
    tld_country_map = {
        "nz": "NZ", "au": "AU", "uk": "UK", "co.uk": "UK",
        "in": "IN", "co.in": "IN", "ca": "CA", "sg": "SG",
        "de": "DE", "fr": "FR", "jp": "JP", "ae": "AE",
        "com": "global", "io": "global", "ai": "global", "co": "global"
    }
    return tld_country_map.get(tld, "global")


def run_fallback_data_collection(company_name: str, website_url: str, linkedin_url: str = None) -> dict:
    """
    Master fallback function. Called when scraping returns < threshold content.
    Routes to the right sources based on company size and country:
      - Large/global companies  → G2, LinkedIn, News, Search
      - Small/local businesses  → Own-site generic pages, Google Maps, Search
      - All companies           → Own-site generic pages always run first

    Returns:
        dict with keys: g2, news, linkedin, search, own_site, maps,
                        confidence_level, fallback_used, sources_found
    """
    print(f"\n[!] FALLBACK MODE TRIGGERED for '{company_name}' — insufficient own-site content.", file=sys.stderr)
    print(f"[*] Running external signal collection...", file=sys.stderr)

    # Detect country to route to appropriate sources
    country = detect_country_from_url(website_url or "")
    print(f"[*] Country detected: {country} for {website_url}", file=sys.stderr)

    # ── STEP 1: Always try own-site generic pages first ───────────────────────
    # Even if no blog/case study, About/Services pages often have useful content
    own_site_data = scrape_own_site_generic_content(website_url or "")

    # ── STEP 2: Google Maps — especially useful for local/small businesses ────
    maps_data = scrape_google_maps(company_name, website_url or "")

    # ── STEP 3: Standard external signals ─────────────────────────────────────
    g2_data       = scrape_g2_reviews(company_name)
    news_data     = scrape_news_mentions(company_name)
    linkedin_data = scrape_linkedin_presence(linkedin_url or "")
    search_data   = scrape_search_presence(company_name, website_url or "")

    # ── Confidence calculation — now includes own_site and maps ───────────────
    sources_found = sum([
        own_site_data["found"],
        maps_data["found"],
        g2_data["found"],
        news_data["found"],
        linkedin_data["found"],
        search_data["found"]
    ])

    # Scale: 6 possible sources now (was 4)
    if sources_found >= 4:
        confidence = "medium"
    elif sources_found >= 2:
        confidence = "low"
    elif sources_found >= 1:
        confidence = "low"
    else:
        confidence = "insufficient"

    print(f"[*] Fallback complete: {sources_found}/6 sources found. Confidence: {confidence.upper()}", file=sys.stderr)

    return {
        "own_site": own_site_data,
        "maps":     maps_data,
        "g2":       g2_data,
        "news":     news_data,
        "linkedin": linkedin_data,
        "search":   search_data,
        "country":  country,
        "confidence_level": confidence,
        "fallback_used": True,
        "sources_found": sources_found
    }