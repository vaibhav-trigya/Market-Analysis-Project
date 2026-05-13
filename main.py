import json
import sys
import os

# Ensure bundled dependencies in temp_libs are accessible
temp_libs_path = os.path.join(os.path.dirname(__file__), "temp_libs")
if os.path.exists(temp_libs_path) and temp_libs_path not in sys.path:
    sys.path.insert(0, temp_libs_path)

import re
import io
import argparse
import random
import time
from playwright.sync_api import sync_playwright # pyrefly: ignore [missing-import] # type: ignore
from agent import MarketIntelligenceAgent, PARTNER_LIST_URL
from analyzer import PartnerAnalyzer
from storage import save_partner_data, save_report, save_report_as_pdf

# Force UTF-8 encoding for stdout to prevent emoji-related crashes on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SEP  = "=" * 60
LINE = "-" * 60

def print_formatted_data(data: dict):
    """Print scraped partner data in a clean, titled, human-readable format."""
    print("\n" + SEP)
    print(f"📋 PARTNER : {data.get('name', 'Unknown')}")
    print(f"🌐 Website : {data.get('website', 'N/A')}")
    print(f"🔗 LinkedIn: {data.get('linkedin', 'N/A')}")
    print(SEP)

    # Overview
    overview = data.get("overview", "")
    if overview:
        print("\n📝 OVERVIEW")
        print(LINE)
        print(overview.strip())

    # Helper to print a category
    def print_category(icon, label, items):
        print(f"\n{SEP}")
        print(f"{icon} {label.upper()}  ({len(items)} found)")
        print(SEP)
        if not items:
            print("  (none found)")
            return
        for i, item in enumerate(items, 1):
            title   = item.get("title", "Untitled")
            link    = item.get("link", "N/A")
            content = item.get("content", "").strip()
            print(f"\n  [{i}] {title}")
            print(f"      🔗 {link}")
            if content and content != "Content extraction failed." and content != "Listing page link - skipping direct content extraction.":
                # Print content, wrapped at 80 chars, indented
                print(f"      📄 Content:")
                for line in content.splitlines():
                    line = line.strip()
                    if line:
                        # Word-wrap at 70 chars
                        while len(line) > 70:
                            print(f"         {line[:70]}")
                            line = line[70:]
                        print(f"         {line}")
            else:
                print(f"      📄 Content: (not available)")

    print_category("📰", "Blogs", data.get("blogs", []))
    print_category("📁", "Case Studies", data.get("case_studies", []))
    print_category("🏆", "Customer Stories", data.get("customer_stories", []))
    print()


from catalyst_client import catalyst_client

def list_existing_partners():
    """List all partners currently in the scraped_data folder AND in the Catalyst Cloud."""
    partners_dict = {} # Use dict to dedup by name/id
    
    # 1. FETCH LOCAL DATA
    output_dir = "scraped_data"
    if os.path.exists(output_dir):
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                if f.endswith(".json"):
                    try:
                        file_path = os.path.join(root, f)
                        with open(file_path, "r", encoding="utf-8") as file:
                            data = json.load(file)
                            key = f"{data.get('name')}_{data.get('partner_id')}"
                            partners_dict[key] = {
                                "name": data.get("name", "Unknown"),
                                "partner_id": data.get("partner_id", "N/A"),
                                "file": f,
                                "path": root,
                                "data": data
                            }
                    except Exception: continue

    # 2. FETCH CLOUD DATA (Stratus)
    if catalyst_client.enabled:
        print("[*] Merging cloud data from Catalyst Stratus...")
        cloud_partners = catalyst_client.list_partners()
        for data in cloud_partners:
            try:
                name = data.get("name", "Unknown")
                partner_id = data.get("partner_id", "N/A")
                key = f"{name}_{partner_id}"
                
                # Cloud data takes precedence if newer, but for now we just fill gaps
                if key not in partners_dict:
                    partners_dict[key] = {
                        "name": name,
                        "partner_id": partner_id,
                        "file": f"cloud_{partner_id}.json",
                        "path": "catalyst://stratus",
                        "data": data
                    }
            except: continue
            
    return list(partners_dict.values())

def show_initial_menu(analyzer: PartnerAnalyzer, agent: MarketIntelligenceAgent):
    """Show the starting menu to the user."""
    while True:
        print("\n" + SEP)
        print("🚀 STRATEGIC COMPETITIVE HUB")
        print(SEP)
        print("  1. Search & Scrape New Company")
        print("  2. Analyze Existing Scraped Entity")
        print("  3. Compare Two Existing Entities (Benchmark)")
        print("  4. Generate Bulk Strategic Report (AI PDF)")
        print("  5. Sync & Refresh All Data (No AI)")
        print("  6. Exit")
        choice = input("\nSelect an option (1-6): ").strip()

        if choice == "1":
            return # Continue to existing interactive scraping loop
        
        elif choice == "2":
            partners = list_existing_partners()
            if not partners:
                print("[-] No scraped data found. Please scrape a partner first.")
                continue
            
            print("\n--- SCRAPED PARTNERS ---")
            for i, p in enumerate(partners, 1):
                print(f"  {i}. {p['name']} ({p['partner_id']})")
            
            try:
                p_idx = input("\nSelect partner to analyze (number): ").strip()
                idx = int(p_idx) - 1
                if 0 <= idx < len(partners):
                    data = partners[idx]['data']
                    summary = analyzer.analyze(data)
                    if summary:
                        data['analysis_summary'] = summary
                        save_partner_data(data)
                        print(SEP)
                        print(f"--- AI ANALYSIS: {data['name']} ---")
                        print(summary)
                        print(SEP)
                else:
                    print("[-] Invalid selection.")
            except ValueError:
                print("[-] Please enter a valid number.")

        elif choice == "3":
            partners = list_existing_partners()
            # Try to find a sensible baseline, default to first
            baseline = next((p for p in partners if "trigya" in p['name'].lower()), partners[0] if partners else None)
            if not baseline:
                print("[-] No scraped data found. Please scrape a company first.")
                continue

            other_partners = [p for p in partners if p != baseline]
            if not other_partners:
                print("[-] No other entities found to compare.")
                continue

            print(f"\n--- SELECT ENTITY TO COMPARE AGAINST {baseline['name']} ---")
            for i, p in enumerate(other_partners, 1):
                print(f"  {i}. {p['name']} ({p['partner_id']})")
            
            try:
                idx = int(input("\nSelect partner (number): ").strip()) - 1
                if 0 <= idx < len(other_partners):
                    p2 = other_partners[idx]
                    p1_data, p2_data = baseline['data'], p2['data']
                    if 'analysis_summary' not in p1_data:
                        p1_data['analysis_summary'] = analyzer.analyze(p1_data)
                        save_partner_data(p1_data)
                    if 'analysis_summary' not in p2_data:
                        p2_data['analysis_summary'] = analyzer.analyze(p2_data)
                        save_partner_data(p2_data)

                    comparison = analyzer.compare(p1_data, p2_data)
                    if comparison:
                        print(SEP)
                        print(f"--- COMPARISON: {p1_data['name']} vs {p2_data['name']} ---")
                        print(comparison)
                        print(SEP)
            except ValueError:
                print("[-] Invalid input.")

        elif choice == "4":
            partners = list_existing_partners()
            # Try to find a sensible baseline
            baseline = next((p for p in partners if "trigya" in p['name'].lower()), partners[0] if partners else None)
            if not baseline:
                print("[-] No scraped data found. Please scrape a company first.")
                continue

            # NEW: Filter competitors to ONLY those in the baseline's competitor folder
            baseline_name_safe = clean_filename(baseline['name'])
            comp_path = os.path.join("scraped_data", baseline_name_safe, "competitors")
            
            other_partners = []
            if os.path.exists(comp_path):
                # Search specifically in this baseline's competitor tree
                for root, dirs, files in os.walk(comp_path):
                    for f in files:
                        if f.endswith(".json"):
                            try:
                                with open(os.path.join(root, f), "r", encoding="utf-8") as file:
                                    c_data = json.load(file)
                                    other_partners.append({"name": c_data['name'], "data": c_data})
                            except: continue
            
            if not other_partners:
                print(f"[-] No competitors found in {comp_path}. Please scrape competitors first.")
                continue

            print(f"[*] Generating Strategic AI Report for {len(other_partners)} ACTIVE competitors...")
            all_to_compare = [baseline] + [{"name": p['name'], "data": p['data']} for p in other_partners]
            
            for p in all_to_compare:
                if 'analysis_summary' not in p['data']:
                    print(f"[*] AI Analysis for {p['name']}...")
                    p['data']['analysis_summary'] = analyzer.analyze(p['data'])
                    save_partner_data(p['data'])
            
            report_content = analyzer.generate_competitive_report(baseline['data'], [p['data'] for p in other_partners])
            if report_content:
                save_report(report_content, f"{baseline['name'].replace(' ', '_')}_Report.txt")
                save_report_as_pdf(report_content, f"{baseline['name'].replace(' ', '_')}_Report.pdf", partners_data=[p['data'] for p in all_to_compare])
                print("\n" + SEP + "\n📊 REPORT GENERATED\n" + SEP)
                print(report_content)

        elif choice == "5":
            # REFRESH FROM COLLECTIONS
            collections_dir = os.path.join(os.getcwd(), "partner_collections")
            discovered_urls = []
            if os.path.exists(collections_dir):
                for f in os.listdir(collections_dir):
                    file_path = os.path.join(collections_dir, f)
                    if os.path.isfile(file_path):
                        with open(file_path, 'r') as file:
                            discovered_urls.extend([l.strip() for l in file.readlines() if "zoho.com" in l])
            
            if not discovered_urls:
                print("[-] No URLs found in partner_collections.")
                continue

            print(f"[*] Starting Bulk Sync: Refreshing {len(discovered_urls)} partners (NO AI)...")
            from playwright.sync_api import sync_playwright # pyrefly: ignore [missing-import] # type: ignore
            with sync_playwright() as pw:
                agent._launch(pw)
                for url in discovered_urls:
                    print(f"[*] Syncing: {url}")
                    try:
                        result = agent.extract_partner_data(url)
                        if result and "name" in result:
                            save_partner_data(result)
                            print(f"[+] Successfully updated: {result['name']}")
                    except Exception as e:
                        print(f"[-] Failed to sync {url}: {e}")
                agent._close()
            print("\n[+] Bulk Sync Complete. Database is fresh.")

        elif choice == "6":
            sys.exit(0)
        else:
            print("[-] Invalid choice.")

def run_interactive(agent: MarketIntelligenceAgent, args):
    analyzer = PartnerAnalyzer()
    
    # Show initial menu before starting scraping loop
    show_initial_menu(analyzer, agent)

    with sync_playwright() as playwright:
        agent._launch(playwright)
        try:
            agent.apply_filters()
            
            while True:
                print("\n" + SEP, file=sys.stderr)
                partner_query = input("Enter partner name or ID (or 'q' to quit): ").strip()
                if partner_query.lower() == 'q':
                    break
                
                if not partner_query:
                    continue
                
                print(f"[*] Searching for {partner_query!r}...", file=sys.stderr)
                agent.partner_name = partner_query
                
                if partner_query.startswith("http"):
                    print(f"[*] Input recognized as URL. Navigating directly.", file=sys.stderr)
                    profile_url = partner_query
                elif re.match(r"^[a-fA-F0-9]{30,}$", partner_query):
                    profile_url = f"https://www.zoho.com/partners/find-partner-profile.html?partnerid={partner_query}"
                    
                    # Check if this ID already exists in scraped data
                    existing_partners = list_existing_partners()
                    existing = next((p for p in existing_partners if p['partner_id'] == partner_query), None)
                    if existing:
                        print(f"[*] Partner ID {partner_query!r} ({existing['name']}) found in local data.", file=sys.stderr)
                        print(f"[*] Re-scraping for latest updates...", file=sys.stderr)
                    else:
                        print(f"[*] Input recognized as Partner ID. Navigating directly.", file=sys.stderr)
                else:
                    search_input = agent.page.locator("input#search-partner")
                    if search_input.count() > 0:
                        search_input.wait_for(state="visible", timeout=10000)
                        search_input.fill("")
                        search_input.fill(partner_query)
                        search_input.press("Enter")
                        agent.page.wait_for_timeout(3000)
                        profile_url = agent._find_matching_card()
                    else:
                        print("[-] Could not find search box on the page.", file=sys.stderr)
                        profile_url = None

                if profile_url:
                    try:
                        manual_links = None
                        if args.manual_links:
                            try:
                                manual_links = json.loads(args.manual_links)
                            except: pass

                        data = agent.extract_partner_data(profile_url, manual_links)
                        
                        # IF NO CONTENT FOUND, PROMPT IN TERMINAL
                        if not data.get("blogs") and not data.get("case_studies") and sys.stdin.isatty():
                            print("\n" + LINE)
                            print("⚠️  No Blogs or Case Studies were found automatically.")
                            do_manual = input("Would you like to provide listing links manually? (y/n): ").strip().lower()
                            if do_manual == 'y':
                                m_links = {}
                                m_links["blog_url"] = input("Enter Blog Listing URL (or leave blank): ").strip()
                                m_links["case_study_url"] = input("Enter Case Study Listing URL (or leave blank): ").strip()
                                m_links["customer_story_url"] = input("Enter Customer Story Listing URL (or leave blank): ").strip()
                                
                                print("[*] Re-scraping with manual links...")
                                data = agent.extract_partner_data(profile_url, m_links)

                        print_formatted_data(data)
                        
                        # Save results to 'scraped_data' folder
                        txt_path = save_partner_data(data)
                        
                        # Interactive Options Menu
                        while True:
                            print("\n[?] What would you like to do next?")
                            print("  1. Standard AI Analysis")
                            print("  2. Compare with another Partner")
                            print("  3. Skip and continue to next search")
                            choice = input("Select an option (1-3): ").strip()
                            
                            if choice == "1":
                                summary = analyzer.analyze(data)
                                if summary:
                                    data['analysis_summary'] = summary
                                    save_partner_data(data)
                                    
                                    print(SEP)
                                    print("--- AI PARTNER ANALYSIS ---")
                                    print(summary)
                                    print(SEP + "\n")
                                    # Analysis is already saved to TXT via save_partner_data if we modify it
                                    # But the previous code appended it manually, let's keep that for the TXT consistency
                                    if txt_path and os.path.exists(txt_path):
                                        with open(txt_path, "a", encoding="utf-8") as f:
                                            f.write("\n" + "="*60 + "\n")
                                            f.write("AI PARTNER ANALYSIS\n")
                                            f.write("="*60 + "\n")
                                            f.write(summary + "\n")
                                break
                            
                            elif choice == "2":
                                partner2_query = input("Enter the second partner ID to compare with: ").strip()
                                if partner2_query:
                                    print(f"[*] Fetching second partner data...", file=sys.stderr)
                                    # We need to navigate and extract partner 2
                                    p2_url = f"https://www.zoho.com/partners/find-partner-profile.html?partnerid={partner2_query}"
                                    try:
                                        data2 = agent.extract_partner_data(p2_url)
                                        save_partner_data(data2) # Save P2 as well
                                        
                                        comparison = analyzer.compare(data, data2)
                                        if comparison:
                                            print(SEP)
                                            print(f"--- COMPARISON: {data['name']} vs {data2['name']} ---")
                                            print(comparison)
                                            print(SEP + "\n")
                                    except Exception as e:
                                        print(f"[-] Failed to fetch second partner: {e}")
                                break
                            
                            elif choice == "3":
                                break
                            else:
                                print("[-] Invalid choice. Please enter 1, 2, or 3.")

                    except Exception as e:
                        print(f"[-] Error: {e}", file=sys.stderr)
                    
                    agent.page.goto(PARTNER_LIST_URL, wait_until="domcontentloaded")
                    agent.apply_filters()
                else:
                    print(f"[-] Could not find partner {partner_query!r}.", file=sys.stderr)
                    
        finally:
            agent._close()

def main():
    parser = argparse.ArgumentParser(description="Zoho Partner Scraper & Analyzer")
    parser.add_argument("--partner", help="Partner name or ID to scrape")
    parser.add_argument("--bulk", action="store_true", help="Generate a bulk competitive report from existing data")
    parser.add_argument("--sync", action="store_true", help="Refresh all partner data from collections (No AI)")
    parser.add_argument("--baseline", help="Partner Name or ID to use as the baseline for bulk report")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--manual-links", type=str, help="JSON string of manual links")
    parser.add_argument("--parent-company", type=str, help="Name of the existing company this is a competitor of")
    
    args = parser.parse_args()
    analyzer = PartnerAnalyzer()

    if args.sync:
        # PURE SCRAPING SYNC (NO AI)
        sync_target_name = "Global Ecosystem"
        
        if args.baseline:
            # TARGETED SYNC: Only sync the baseline and its mapped competitors
            partners = list_existing_partners()
            baseline = next((p for p in partners if args.baseline.lower() in p['name'].lower() or args.baseline == p['partner_id']), None)
            
            if baseline:
                sync_target_name = baseline['name']
                
                # Determine targets based on folder structure (same logic as reporting)
                is_competitor_file = "competitors" in baseline['path']
                if is_competitor_file:
                    # SIBLING MODE: Sync all competitors in the same folder
                    parent_dir = os.path.dirname(baseline['path'])
                    targets = [p for p in partners if os.path.dirname(p['path']) == parent_dir]
                else:
                    # STANDARD MODE: Sync parent + all its competitors
                    baseline_folder_name = baseline['name'].replace(' ', '_')
                    competitors = [
                        p for p in partners 
                        if (f"{baseline_folder_name}{os.sep}competitors" in p['path'] or f"{baseline_folder_name}/competitors" in p['path'])
                    ]
                    targets = [baseline] + competitors

                print(f"[*] Targeted Sync: identified {len(targets)} entities for {baseline['name']} tree.")
            else:
                print(f"[-] Baseline '{args.baseline}' not found for sync. Check naming.")
                return
        else:
            # GLOBAL SYNC: Use all existing partners
            targets = list_existing_partners()
        
        if not targets:
            print("[-] No partners found to sync.")
            return

        total = len(targets)
        print(f"[*] Starting High-Precision Sync: Refreshing {total} partners for {sync_target_name}...")
        
        def write_progress(current, total_count, status_text):
            try:
                import json
                with open("sync_progress.json", "w") as f:
                    json.dump({"current": current, "total": total_count, "status": status_text}, f)
            except: pass


        with sync_playwright() as pw:
            agent = MarketIntelligenceAgent(headless=args.headless)
            agent._launch(pw)
            try:
                print("[*] Establishing Zoho session context...", file=sys.stderr)
                agent.page.goto(PARTNER_LIST_URL, wait_until="load", timeout=40000)
                agent.page.wait_for_timeout(3000)
                
                for i, target in enumerate(targets):
                    write_progress(i + 1, total, f"Syncing: {target['name']}")
                    print(f"[*] Syncing {i+1}/{total}: {target['name']}")
                    
                    try:
                        if i > 0:
                            delay = random.uniform(2, 5)
                            time.sleep(delay)
                        
                        # 1. Use existing website if we have it (Universal Scraping)
                        # This skips the Zoho profile intermediary which often contains wrong links
                        target_url = target['data'].get('website')
                        
                        # Fallback to Zoho profile if website is missing
                        if not target_url or "zoho.com" in target_url:
                            pid = target.get('partner_id')
                            if pid and pid != "N/A":
                                target_url = f"https://www.zoho.com/partners/find-partner-profile.html?partnerid={pid}"
                        
                        if not target_url:
                            print(f"[-] Skipping {target['name']}: No URL found.")
                            continue

                        result = agent.extract_partner_data(target_url)
                        if result and "name" in result:
                            # Re-save data
                            save_partner_data(result)
                            # Perform AI Re-analysis
                            summary = analyzer.analyze(result)
                            if summary:
                                result['analysis_summary'] = summary
                                save_partner_data(result)
                            print(f"[+] Successfully updated & analyzed: {result['name']}")
                    except Exception as e:
                        print(f"[-] Failed to sync {target['name']}: {e}")
            finally:
                agent._close()
                if os.path.exists("sync_progress.json"):
                    try: os.remove("sync_progress.json")
                    except: pass
        print(f"[+] Sync Complete for {sync_target_name}.")
        print("\nSUCCESS: SYNC COMPLETE.")
        return

    if args.bulk:
        # PURE AI REPORT GENERATION
        partners = list_existing_partners()
        if not partners:
            print("[-] No partners found in scraped_data.")
            return

        if args.baseline:
            # Try to find partner by ID or Name
            baseline = next((p for p in partners if args.baseline.lower() in p['name'].lower() or args.baseline == p['partner_id']), None)
            if not baseline:
                print(f"[-] Baseline partner '{args.baseline}' not found. Defaulting to first available.")
                baseline = partners[0]
        else:
            # If run from dashboard or pipe, don't ask for input
            if not sys.stdin.isatty():
                baseline = next((p for p in partners if "trigya" in p['name'].lower()), partners[0])
            else:
                print("\n--- SELECT BASELINE PARTNER FOR COMPARISON ---")
                for i, p in enumerate(partners, 1):
                    print(f"  {i}. {p['name']} ({p['partner_id']})")
                
                try:
                    choice = input("\nSelect partner to analyze against market (number, default: 1): ").strip()
                    if not choice:
                        baseline = partners[0]
                    else:
                        baseline = partners[int(choice)-1]
                except:
                    baseline = partners[0]

        # Determine competitors based on folder structure AND logical metadata
        is_competitor_file = "competitors" in baseline['path']
        baseline_name = baseline['name']
        baseline_folder_name = baseline_name.replace(' ', '_')
        active_comp_dir = os.path.abspath(os.path.join("scraped_data", baseline_folder_name, "competitors"))
        
        other_partners = []
        for p in partners:
            if p['partner_id'] == baseline['partner_id']:
                continue
            
            # IDENTITY SHIELD: Skip failed scrapes or blocked pages to prevent pollution
            p_name = p.get('name', '').lower()
            if any(junk in p_name for junk in ["checking your browser", "just a moment", "access denied", "enable javascript"]):
                continue
            if p == baseline: continue
            
            # 1. PHYSICAL CHECK: Is it in the local competitor folder?
            p_abs_path = os.path.abspath(p['path'])
            if p_abs_path.startswith(active_comp_dir):
                other_partners.append(p)
                continue
                
            # 2. CLOUD CHECK: Is it a cloud-only partner linked to this baseline?
            if p['path'] == "catalyst://stratus":
                parent_name = p['data'].get('relationship', {}).get('parent_company')
                if parent_name and parent_name.lower() == baseline_name.lower():
                    other_partners.append(p)

        if is_competitor_file:
            print(f"[*] Baseline identified as a Competitor. Enabling Peer Sibling Analysis mode.")
        
        if not other_partners and args.baseline:
            print(f"[*] No specific competitors found for {baseline['name']}. Report will be baseline-only.")

        comp_names = ", ".join([p['name'] for p in other_partners]) if other_partners else "None"
        print(f"[*] Generating Strategic AI Report: {baseline['name']} vs {len(other_partners)} local competitors ({comp_names})...")
        
        # Ensure ONLY the baseline has an AI summary (most important for accuracy)
        if 'analysis_summary' not in baseline['data']:
            print(f"[*] Analyzing Baseline: {baseline['name']}...")
            baseline['data']['analysis_summary'] = analyzer.analyze(baseline['data'])
            save_partner_data(baseline['data'])
        
        # Prepare all data for the unified bulk analysis pass
        all_to_compare = [baseline] + other_partners
        
        report_json = analyzer.generate_competitive_report(baseline['data'], [p['data'] for p in other_partners])
        if report_json:
            rep_name = f"{baseline['name'].replace(' ', '_')}_Analysis.pdf"
            save_report_as_pdf(report_json, rep_name, partners_data=[p['data'] for p in all_to_compare])
            print(f"[+] Strategic Report Generated for {baseline['name']}.")
            
            # Print usage for dashboard
            print(f"TOKEN_USAGE: {json.dumps(analyzer.total_usage)}")
            print("\nSUCCESS: ANALYSIS COMPLETE.")
        else:
            print("[-] Competitive Report generation failed.")
            sys.exit(1)
        return

    # EXISTING INTERACTIVE OR SINGLE SCRAPE LOGIC
    partner_name = args.partner
    agent = MarketIntelligenceAgent(
        partner_name=partner_name, 
        headless=args.headless,
        parent_company=args.parent_company
    )

    if not partner_name:
        # Interactive loop mode
        run_interactive(agent, args)
    else:
        # Automated Single Partner Scrape & Analyze
        try:
            profile_url = None
            # 1. If a full URL was passed
            if partner_name.startswith("http"):
                profile_url = partner_name
                print(f"[*] Navigating directly to URL: {profile_url}")
            
            # 2. If a raw hex partner ID was passed
            elif re.match(r"^[a-fA-F0-9]{30,}$", partner_name):
                profile_url = f"https://www.zoho.com/partners/find-partner-profile.html?partnerid={partner_name}"
                print(f"[*] Navigating directly to Partner ID: {partner_name}")
            
            if profile_url:
                with sync_playwright() as pw:
                    agent._launch(pw)
                    try:
                        manual_links = None
                        if args.manual_links:
                            try:
                                manual_links = json.loads(args.manual_links)
                            except: pass
                        result = agent.extract_partner_data(profile_url, manual_links)
                    finally:
                        agent._close()
            else:
                result = agent.run()

            if isinstance(result, dict) and "name" in result:
                # Folder normalization for logs
                folder_name = result['name'].replace(" ", "_").replace("/", "_").replace("\\", "_")
                print(f"[+] Intelligence saved to: scraped_data/{folder_name}/")
                save_partner_data(result)
                summary = analyzer.analyze(result)
                if summary:
                    result['analysis_summary'] = summary
                    save_partner_data(result)
                    print(f"[+] Scrape & Analysis complete for {result['name']}.")
                    
                    # Print usage for dashboard
                    print(f"TOKEN_USAGE: {json.dumps(analyzer.total_usage)}")
                    print("\nSUCCESS: ANALYSIS COMPLETE.")
        except Exception as e:
            print(f"[-] Error during automated scrape: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()



