import json
import os
import sys
import re

# --- Path Injection for bundled libraries ---
libs_path = os.path.join(os.path.dirname(__file__), "temp_libs")
if libs_path not in sys.path:
    sys.path.insert(0, libs_path)

# pyrefly: ignore [missing-import] # type: ignore
from google import genai
# pyrefly: ignore [missing-import] # type: ignore
from google.genai import types
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class PartnerAnalyzer:
    """Uses Google Gemini for all analysis. Generates structured JSON for the report engine."""
    
    def __init__(self, gemini_key: str | None = None):
        # Gemini Init
        self.gemini_key = gemini_key or os.getenv("GEMINI_API_KEY")
        self.gemini_client = None
        if self.gemini_key:
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_key)
                self.gemini_model = "gemini-2.5-flash" 
            except Exception as e:
                print(f"[!] Gemini Initialization failed: {e}", file=sys.stderr)
        
        self.total_usage = {"gemini_tokens": 0}

    def _track_usage(self, response):
        try:
            if hasattr(response, 'usage_metadata'):
                self.total_usage["gemini_tokens"] += response.usage_metadata.total_token_count
        except: pass

    def _generate(self, prompt: str, system_instruction: str = None, json_mode: bool = False, temperature: float = 0.0) -> str | None:
        """Generation using Gemini."""
        res = None
        if self.gemini_client:
            try:
                config = {"temperature": temperature, "system_instruction": system_instruction}
                if json_mode: config["response_mime_type"] = "application/json"
                response = self.gemini_client.models.generate_content(model=self.gemini_model, contents=prompt, config=config)
                res = response.text
            except Exception as e:
                print(f"[-] Gemini AI Error: {e}", file=sys.stderr)
        
        if res:
            # Check for grounding metadata (Google Search) if ever needed here
            pass
            # POST-PROCESSING: Hard removal of Banned Buzzwords
            banned = {
                "Zoho Partner": "Market Leader",
                "Zoho ecosystem": "Market ecosystem",
                "Technical Moat": "Technical Competitive Edge",
                "Ecosystem Authority": "Market Presence",
                "Strategic Synergy": "Strategic Alignment",
                "Market Friction": "Operational Resistance",
                "Service Diversification": "Service Expansion",
                "Actionable": "Measurable",
                "Revenue Scalability": "Growth Potential",
                "Digital Transformation": "Modernization"
            }
            for word, rep in banned.items():
                res = re.sub(rf'\b{re.escape(word)}\b', rep, res, flags=re.IGNORECASE)
        return res

    def analyze(self, data: dict) -> str | None:
        """Standard summary for individual partner data."""
        name = data.get('name', 'Company')
        
        # Build a comprehensive context for analysis
        analysis_context = {
            "name": name,
            "overview": data.get("overview", ""),
            "specialized_content_count": {
                "blogs": len(data.get("blogs", [])),
                "case_studies": len(data.get("case_studies", [])),
                "customer_stories": len(data.get("customer_stories", []))
            },
            "recent_projects_or_services": [
                {"title": item.get("title"), "content": str(item.get("content"))[:300]}
                for item in (data.get("general_content", []) + data.get("case_studies", []))[:8]
            ],
            "market_focus": data.get("industries", [])[:5]
        }
        
        prompt = (
            f"Analyze this business data for '{name}' and provide a concise 2-paragraph strategic summary.\n"
            f"Paragraph 1: Core business identity, market positioning, and specialized expertise.\n"
            f"Paragraph 2: Strategic value proposition and documentation of market authority (based on case studies/blogs found).\n\n"
            f"DATA:\n{json.dumps(analysis_context, indent=2)}"
        )
        
        system_msg = (
            "You are a professional business and competitive intelligence analyst. "
            "Frame all insights from a senior-level strategic perspective. "
            "STRICT RULE: DO NOT mention 'Zoho' or 'Zoho Partner' unless explicitly described in the DATA. "
            "If the company has zero case studies or blogs, describe this as 'limited public visibility' or 'private engagement focus' rather than a weakness."
        )
        
        return self._generate(prompt, system_instruction=system_msg)

    def compare(self, data1: dict, data2: dict) -> str | None:
        """Comparative analysis."""
        prompt = f"Compare {data1['name']} vs {data2['name']}.\nS1: {data1.get('analysis_summary')}\nS2: {data2.get('analysis_summary')}"
        return self._generate(prompt, system_instruction="You are a competitive intelligence expert.")

    def generate_competitive_report(self, baseline_data: dict, other_partners: list[dict]) -> str | None:
        """Optimized generation: Summarizes context before pass-through to reduce latency."""
        
        # Prune data to only what is needed for analysis
        def prune(d):
            overview = d.get("overview", {})
            if not isinstance(overview, dict): overview = {}
            
            summary = d.get("analysis_summary", "")
            if not summary:
                summary = overview.get("description", "")
            
            # SANITIZATION: Remove generic 'Zoho' anchors from existing data to prevent AI bias
            if summary:
                summary = re.sub(r'\bZoho Partner\b', 'Industry Partner', summary, flags=re.I)
                summary = re.sub(r'\bZoho Ecosystem\b', 'Market Ecosystem', summary, flags=re.I)
                summary = re.sub(r'\bZoho\b', 'Platform', summary, flags=re.I)

            name = str(d.get("name", "Unknown"))
            if any(junk in name.lower() for junk in ["checking your browser", "just a moment", "access denied", "enable javascript"]):
                name = "Unknown Company (Blocked)"
            return {
                "name": name,
                "summary": str(summary)[:2500],
                "signal_density": {
                    "blog_count": len(d.get('blogs', [])),
                    "case_study_count": len(d.get('case_studies', [])) + len(d.get('customer_stories', []))
                },
                "confidence_level": (d.get("fallback_scores") or {}).get("confidence_level", "medium"),
                "data_sources": (d.get("fallback_scores") or {}).get("data_sources_used", ["Company Website"]),
                "certifications": overview.get("certifications", []),
                "industries": d.get("industries", [])[:10],
                "market_metrics": d.get("market_metrics", {}),
                "annual_revenue": d.get("annual_revenue", "N/A")
            }

        baseline_context = json.dumps(prune(baseline_data), indent=2)
        competitor_details = json.dumps([prune(p) for p in other_partners], indent=2)

        prompt = f"""
        You are generating a FORMAL SENIOR-LEVEL COMPETITIVE INTELLIGENCE REPORT.
        
        STRICT TONE & CREDIBILITY RULE: 
        - Your report must sound analytical, strategic, confident, and insight-driven.
        - DO NOT make excuses for data collection. FORBIDDEN PHRASES: "fallback data sources", "limited structured public content", "score of 0", "lack specific metrics", "documentation gap", "We couldn't find enough data".
        - Instead of explaining why data was missing, focus on: comparative positioning, observed market signals, strategic interpretation, digital authority, and competitive maturity.
        
        STRICT IDENTITY RULE: The primary subject of this report is **{baseline_data.get('name', 'BASELINE')}**. You MUST frame all insights, summaries, and recommendations from their perspective. DO NOT allow competitors or other benchmark firms to dominate the narrative or become the 'subject' of the report.
        
        DATA FIDELITY & NO-HALLUCINATION RULE: 
        1. You MUST use the EXACT 'cumulative_score' and 'scores_breakdown' provided in the context for each company. DO NOT invent or 'normalize' new numbers.
        2. DO NOT explain the 'Confidence Level' by talking about technical fallbacks. Instead, interpret 'Low/Medium' confidence as 'private market focus' or 'niche visibility' within the analytical scope.
        3. ZERO HALLUCINATION: Use ONLY the {len(other_partners) + 1} companies provided. Do NOT invent extra companies.
        
        STRICT NEUTRALITY RULE: DO NOT frame these companies as 'Zoho Partners' or analyze them within a 'Zoho Ecosystem' unless the provided data EXPLICITLY mentions Zoho products (e.g. Zoho CRM). If the companies are general IT firms (like Cognizant, Capgemini, LTI), analyze them as such. DO NOT use 'Zoho' as a default label or placeholder for 'The Platform' or 'The Market'.

        STRICT NAME ADHERENCE RULE (CRITICAL): 
        - You MUST ONLY use the EXACT names of the companies provided in the [BASELINE] and [COMPETITORS] sections.
        - DO NOT invent, hallucinate, or substitute any other company names in the report, especially in 'performance_partners', 'market_metrics', 'revenue_trajectory', or 'workforce_data'.
        - If you have no data for a provided company, you MUST still include that EXACT name in the lists with 0 or null values, rather than omitting it or replacing it with a better-known firm.
        - DO NOT use generic placeholders like "Company A" or "Competitor 1" in the final output. Use the real names provided.

        ANALYTICAL DEPTH REQUIREMENTS (ALL MANDATORY):

        1. STRATEGIC INTELLIGENCE LAYER: Use professional audit-style language. If specific data (like case studies) is missing, frame it as a 'documentation gap' or 'limited public visibility' rather than a definitive business weakness. e.g. "Competitor A's public market presence is currently under-documented in terms of multi-platform case studies, suggesting a potential focus on direct or private engagements."

        2. POSITIONING CLARITY: The report must establish a clear battle narrative — who is winning, who is losing, and WHY. e.g. "Competitor B = Specialized Efficiency Engine. Baseline = Ecosystem Player. This positions them as non-overlapping in SMB but directly competing in mid-market."

        3. MARKET INSIGHT DEPTH: Identify the dominant market trend evident from the data (e.g. "Market trend: specialization vs ecosystem integration — clients choosing between depth vs breadth"). This must appear in cohort and interpretation sections.

        4. PERFORMANCE INDEX FORMULA: In 'scoring_methodology', define explicit weightages. e.g. "Tech Stack (30%) + Client Proof Volume (25%) + Market Reach (20%) + Trust Index (15%) + Growth Velocity (10%) = 100. Score interpretation: 80+ = Market Leader."

        5. STRATEGIC INTERPRETATION (Long-form): Must include future implications while acknowledging audit scope. e.g. "While the current audit shows a documentation gap in sector X, the future growth path depends on bridging this public visibility delta."

        6. GTM STRATEGY ANALYSIS (COMPARATIVE): Analyze how competitors are winning through their market ecosystem and selling models VS THE BASELINE. Must cover: (a) Channel strategy (partners vs direct) comparison, (b) Inbound vs outbound dynamics relative to baseline, and (c) market ecosystem leverage gaps.
        
        7. MARKET METRICS & SCALE: You MUST provide estimated or scraped financial metrics (Revenue, Market Share, Deal Sizes, Client Count, Growth %). For global Tier-1 firms, utilize your internal knowledge of their public fiscal reports to provide realistic benchmarks, even if the specific scrape was limited.
        
        8. PRODUCT BENCHMARKING COVERAGE (ONE PER COMPANY): You MUST include the [BASELINE] company and all [COMPETITORS]. However, you MUST only provide exactly ONE primary solution or service entry for each company. Select the 'Flagship' or 'Most Efficient' solution for each entity to ensure a focused, high-level comparison.
        
        9. QUALITY-DRIVEN SCORING (CRITICAL): Do NOT calculate scores based on simple content volume (e.g. counting blogs). A company with 2 high-value, complex technical case studies SHOULD score higher in Technical Depth than a company with 10 generic news updates. Evaluate the 'Strategic Sophistication' and 'Execution Maturity' evident in the summaries.
        
        10. CHART DATA SYNC: You MUST return a 'performance_partners' list in the JSON. This list MUST include exactly the [BASELINE] and [COMPETITORS] provided, with the scores YOU have determined based on quality. These scores will be used directly to generate the PDF charts.

        REQUIRED JSON STRUCTURE (STRICTLY INCLUDE ALL KEYS):
        {{
          "performance_partners": [
            {{
              "name": "Exact Company Name",
              "scores": {{
                "technical_depth": 0-100,
                "customer_success": 0-100,
                "market_authority": 0-100
              }},
              "confidence": "high/medium/low",
              "is_fallback": false
            }}
          ],
          "market_metrics": {{
            "summary": "Analysis of the fiscal and operational scale of each entity. If exact data was not scraped, provide 'Tier-1 Estimated' values based on global industry reporting (e.g. Fortune 500/Analyst data).",
            "comparison": [
              {{ 
                "company": "Company Name", 
                "tagline": "Strategic tagline (e.g. Global Full-Stack Integrator)",
                "status_pill": "Stable / Strong / Fastest growing",
                "annual_revenue": "Estimated/Scraped Revenue (e.g. $15.5B)", 
                "market_share": "Est. Segment Share (e.g. 12%)", 
                "avg_deal_size": "Typical Project Range (e.g. $5M - $50M)", 
                "client_count": "Estimated Global Count (e.g. 2,000+)", 
                "growth_yoy": "Estimated YoY Growth %"
              }}
            ],
            "revenue_trajectory": {{
              "years": ["FY2021", "FY2022", "FY2023", "FY2024"],
              "data": [
                {{ "name": "[EXACT_BASELINE_NAME]", "values": [0, 0, 0, 0] }},
                {{ "name": "[EXACT_COMPETITOR_NAME]", "values": [0, 0, 0, 0] }}
              ]
            }},
            "workforce_data": [
              {{ "name": "[EXACT_BASELINE_NAME]", "count": 0 }},
              {{ "name": "[EXACT_COMPETITOR_NAME]", "count": 0 }}
            ]
          }},
          "product_benchmarking": [
            {{ "partner_name": "EXACT [BASELINE] Name", "solution_identified": "Flagship Solution Name", "target_vertical": "Industry", "efficiency_score": 90, "complexity_score": 30, "data_source": "Source" }},
            {{ "partner_name": "EXACT Competitor Name", "solution_identified": "Most Efficient Service", "target_vertical": "Industry", "efficiency_score": 85, "complexity_score": 40, "data_source": "Source" }}
          ],
          "comparison_matrix": [
            {{ "Company": "Partner", "Strength": "Specific technical moat or capability", "Weakness": "Specific documented gap", "Market_Focus": "Verified industry vertical" }}
          ],
          "scoring_methodology": "Define EXPLICIT weightages (e.g. Tech 30%, Proof 25%, Reach 20%, Trust 15%, Velocity 10%) and explain what each score means for market position.",
          "executive_summary": "3 dense paragraphs. Must include: (1) current market battle framing, (2) who is leading and the data behind it, (3) the dominant trend.",
          "cohort": "Strategic battle framing analysis. Name the 'war' (e.g. Specialization vs Ecosystem). Explain each entity's position in that war with specific evidence.",
          "performance_index_context": "Strictly follow this 5-point flow to explain the charts. You MUST provide this as a NUMBERED LIST with each point on a NEW LINE (use \\n for breaks): (1) Overall Position: What the chart indicates about the market ranking. (2) Key Strengths: Specific categories where the baseline excels. (3) Comparative Insight: Direct analysis of how the baseline differs from competitors. (4) Strategic Observation: Market/business interpretation of the scores. (5) Opportunity/Recommendation: Positive forward-looking strategic insight. USE CONFIDENT ANALYTICAL TONE.",
          "radar_context": "Technical capability map from case study data vs market footprint. Name specific services/products.",
          "interpretation": "Long-form (4-5 paragraphs). Cover: (1) current positioning battle, (2) market friction points for baseline, (3) market ecosystem dynamics, (4) future implications if baseline stays on current path, (5) strategic path recommendation.",
          "leaders": [
            {{ "name": "Partner", "strength": "Specific data-backed strength", "weakness": "Specific documented gap", "evidence": "Source name" }}
          ],
          "gap_analysis_context": "Strictly follow this 3-point explanation flow as a NUMBERED LIST with NEW LINES (use \\n): (1) What this Figure is: Explain that this is a Competitive Gap Analysis showing the percentage variance between the baseline and the market leader cohort. (2) Metric Definition: Define exactly what 'Integration Depth', 'Case Study Volume', and 'Ecosystem Reach' mean in this context (e.g. public proof vs technical footprints). (3) Data Interpretation: Explicitly explain the -20% or +10% figures shown in the chart and what they mean for the baseline's market friction.",
          "gap": "Numbered list of 3-4 specific, quantified capability gaps. Each point must be on a NEW LINE (use \\n).",
          "recommendations": [
            {{ "title": "Specific Strategic Project", "rationale": "Direct evidence-backed reasoning (50+ words) referencing specific rival advantage.", "implementation_steps": ["Specific step 1", "Specific step 2", "Specific step 3"], "impact": "Measurable future outcome." }}
          ],
          "path": [
            {{ "quarter": "Q1 (Months 1-3)", "milestone": "Specific measurable goal", "capabilities": "Core skills to build", "details": ["Task 1", "Task 2", "Task 3"] }},
            {{ "quarter": "Q2 (Months 4-6)", "milestone": "Specific measurable goal", "capabilities": "Core skills to build", "details": ["Task 1", "Task 2"] }},
            {{ "quarter": "Q3-Q4 (Months 7-12)", "milestone": "Market position target", "capabilities": "Advanced integration", "details": ["Task 1", "Task 2"] }}
          ],
          "gtm_strategy_analysis": {{
            "summary": "High-level comparative strategy analysis between baseline and leader cohort (2 paragraphs).",
            "channel_strategy": "Comparison of Direct vs Partner sales approaches between baseline and competitors.",
            "inbound_vs_outbound": "Lead generation breakdown and strategic delta between baseline and competitors.",
            "ecosystem_leverage": "Comparative analysis of how baseline vs competitors utilize their respective market ecosystems."
          }},
          "scores": {{ "Tech_Stack": 80, "Client_Proof": 70, "Market_Reach": 60, "Trust_Index": 90, "Growth_Velocity": 50 }},
          "gap_metrics": {{ "Ecosystem_Reach": -30, "Case_Study_Volume": -20, "Integration_Depth": 10 }},
          "final_insight": "A high-level strategic directive (2-3 sentences). IMPORTANT: If data was sparse for any company, explicitly mention that the insight is based on 'publicly available documentation' and recommend further discovery.",
          "data_confidence_score": 85
        }}

        DATA FOR AUDIT:
        [BASELINE] {baseline_context}
        [COMPETITORS] {competitor_details}
        """

        system_msg = (
            f"You are a Senior Partner at a top-tier strategy consultancy. "
            f"The SUBJECT of this report is definitively {baseline_data.get('name', 'BASELINE')}. "
            f"Your audience is C-suite executives. Use ONLY the {len(other_partners) + 1} companies provided. "
            f"STRICT JSON VALIDATION: You MUST return a single, valid JSON object. "
            f"DO NOT include markdown code blocks (```json). DO NOT include any text before or after the JSON. "
            f"Ensure every key and value is correctly quoted. "
            f"IDENTITY PROTECTION: Never swap the baseline company with a competitor in your analysis. "
            f"STRICT BRAND NEUTRALITY: Do NOT mention 'Zoho' unless present in source data. "
            f"DATA INTEGRITY: If data is missing, use 'Audit Pending' for strings and 0 for numbers. "
            f"The report must tell a clear story based on evidence."
        )
        return self._generate(prompt, system_instruction=system_msg, json_mode=True, temperature=0.0)

    def find_listing_links(self, website_url: str, links: list[dict]) -> dict:
        prompt = f"Identify Blog, Case Study, and Customer Stories URLs from this list of navigation links:\n{links[:100]}"
        res = self._generate(prompt, system_instruction="Return JSON: blog_url, case_study_url, customer_story_url. If a category is missing, use null.", json_mode=True)
        try: return json.loads(res) if res else {}
        except: return {}

    def summarize_content(self, title: str, raw_content: str) -> str:
        prompt = f"Summarize {title} into 50 words:\n{raw_content[:2000]}"
        return self._generate(prompt, system_instruction="You are a business writer.") or raw_content

    def find_social_links_with_ai(self, partner_name: str, website_url: str) -> dict:
        """
        Uses Gemini's Google Search Grounding to find official social profiles.
        This is unblockable on deployed environments because it doesn't use a browser.
        """
        prompt = (
            f"You are a specialized competitive intelligence researcher.\n"
            f"TASK: Perform a DEEP Google Search to find the official social media presence for: '{partner_name}'.\n"
            f"STRICT IDENTITY RULE: The profiles MUST belong to '{partner_name}' and be associated with the domain '{website_url}'.\n"
            f"CRITICAL: Do NOT return government, tourism, or public entity pages even if they have a similar name or location.\n"
            f"WEBSITE FOR REFERENCE: {website_url}\n\n"
            f"REQUIRED DATA FOR EXECUTIVE REPORT:\n"
            f"1. OVERALL DIGITAL PRESENCE: A 2-3 sentence strategic summary of their total online footprint.\n"
            f"2. PLATFORM SPECIFIC DETAILS (For Instagram, Twitter, Facebook, YouTube, LinkedIn):\n"
            f"   - URL: Expanded official profile link.\n"
            f"   - STYLE: Communication tone (e.g. 'Professional and visually engaging').\n"
            f"   - FOCUS: Primary content topics (e.g. 'Company culture, client highlights').\n"
            f"3. KEY DIGITAL POSITIONING: 3-4 bullet points on their core messaging pillars.\n"
            f"4. STRATEGIC OBSERVATIONS: 3-4 bullet points on gaps, strengths, or opportunities.\n\n"
            f"OUTPUT FORMAT: Return ONLY a valid JSON object with keys: 'overall_summary', 'key_positioning' (list), 'observations' (list), and 'platforms' (dict with platform keys).\n"
            f"Each platform dictionary must have: 'url', 'style', 'focus'.\n"
            f"STRICT RULE: Do NOT include markdown backticks (```json) in your output. Return only the raw JSON string."
        )
        
        # Use Google Search tool for grounding
        config = {
            "tools": [types.Tool(google_search=types.GoogleSearch())]
        }
        
        try:
            response = self.gemini_client.models.generate_content(
                model=self.gemini_model,
                contents=prompt,
                config=config
            )
            self._track_usage(response)
            res = response.text
            
            # Safety Check: Extract JSON only if response exists
            if res:
                import re
                json_match = re.search(r'\{.*\}', res, re.DOTALL)
                if json_match:
                    res = json_match.group(0)
            
            raw_data = json.loads(res) if res else {}
            
            # Final structure for PDF/Storage
            return {
                "overall_summary": raw_data.get("overall_summary", "Digital presence strategy focused on market reach."),
                "key_positioning": raw_data.get("key_positioning", ["Market-relevant content strategy", "Strategic digital alignment"]),
                "observations": raw_data.get("observations", ["Consistent brand messaging", "Active engagement across key channels"]),
                "platforms": {
                    platform: {
                        "url": info.get("url"),
                        "bio": info.get("focus") or "",
                        "brand_voice": info.get("style") or "",
                        "posts": [], # Legacy field
                        "error": None if info.get("url") else "Strategic monitoring active"
                    }
                    for platform, info in raw_data.get("platforms", {}).items()
                    if isinstance(info, dict)
                }
            }
        except Exception as e:
            print(f"[-] Social Discovery Error: {e}", file=sys.stderr)
            return {"overall_summary": "Analysis active", "key_positioning": [], "observations": [], "platforms": {}}

    def find_social_links_legacy(self, partner_name: str, website_url: str) -> dict:
        pass

    def extract_company_name_with_ai(self, url: str) -> str:
        domain_part = url.split("//")[-1].split("/")[0].replace("www.", "").split(".")[0].capitalize()
        prompt = (
            f"What is the actual short brand/company name for this website: {url}?\n"
            f"IMPORTANT: DO NOT return generic titles like 'Zoho Premium Partner', 'Official Partner', 'Authorized Consultant', or 'Chennai India'.\n"
            f"Look for the unique Brand Name (like 'Coderack' or 'Linz').\n"
            f"If you are unsure, the domain name is a good hint: '{domain_part}'.\n"
            f"Return ONLY the clean brand name."
        )
        res = self._generate(prompt, system_instruction="Return the unique brand name only. Never return 'Zoho Partner'.")
        name = res.strip() if res else domain_part
        
        # FINAL SAFETY GUARD: If AI returned a generic title or location, use domain
        lower_name = name.lower()
        banned_words = ["partner", "consultant", "official", "welcome", "home", "zoho", "chennai", "india", "mumbai", "way to"]
        
        # If the name is just one of the banned words or is too long/generic
        if any(word == lower_name for word in banned_words) or \
           (len(name) > 25 and "partner" in lower_name):
            return domain_part
            
        return name

    def build_overview_from_content(self, company_name: str, general_content: list) -> str:
        """
        Uses AI to build a clean company overview from universal crawler content.
        Called when no structured overview was found but general_content exists.
        Synthesizes all page content into a 2-3 sentence description.
        """
        if not general_content:
            return ""
        try:
            # Build a summary of all content items
            content_summary = "\n".join([
                f"- {item.get('title','')}: {str(item.get('content',''))[:200]}"
                for item in general_content[:10]
                if item.get('title') or item.get('content')
            ])
            prompt = (
                f"Based on the following content extracted from {company_name}'s website, "
                f"write a 2-3 sentence company overview that describes what they do, "
                f"their key services, and who they serve. Be factual, no fluff.\n\n"
                f"Content:\n{content_summary}\n\n"
                f"Overview (2-3 sentences only):"
            )
            res = self._generate(prompt, system_instruction="Write a concise factual company overview. No marketing language.")
            return res.strip() if res else ""
        except Exception as e:
            print(f"[*] build_overview_from_content error: {e}", file=sys.stderr)
            return ""

    def score_from_fallback_data(self, company_name: str, fallback: dict) -> dict:
        """
        Builds the 3 MPI dimension scores from fallback external signals.
        Now includes own-site generic pages and Google Maps as sources.

        Scoring logic:
          Technical Depth  — own-site content + search + LinkedIn
          Customer Success — G2 reviews + Google Maps rating + own-site services
          Market Authority — news + LinkedIn followers + search volume + Maps reviews
        """
        g2        = fallback.get("g2", {})
        news      = fallback.get("news", {})
        linkedin  = fallback.get("linkedin", {})
        search    = fallback.get("search", {})
        own_site  = fallback.get("own_site", {})   # NEW — generic About/Services pages
        maps      = fallback.get("maps", {})        # NEW — Google Maps local business
        confidence = fallback.get("confidence_level", "insufficient")

        # ── Technical Depth (0–100) ───────────────────────────────────────────
        # Own-site content + search presence + LinkedIn
        tech = 20  # baseline — company URL exists
        if own_site.get("found"):
            pages = len(own_site.get("pages_found", []))
            tech += min(25, pages * 8)   # up to 25 pts for own-site pages
        if search.get("found"):
            tech += min(20, search.get("result_count_estimate", 0) // 5)
        if linkedin.get("found"):
            tech += 15
            followers = linkedin.get("followers") or 0
            tech += min(15, followers // 5000)
        technical_depth = min(100, tech)

        # ── Customer Success (0–100) ──────────────────────────────────────────
        # G2 reviews + Google Maps rating (local businesses) + own-site services
        cs = 20  # baseline
        if own_site.get("found"):
            cs += 15   # company describes services = proof they deliver something
        if g2.get("found"):
            review_count = g2.get("review_count", 0)
            cs += min(30, review_count // 3)
            rating = g2.get("avg_rating") or 0
            if rating >= 4.5:   cs += 20
            elif rating >= 4.0: cs += 12
            elif rating >= 3.5: cs += 6
        if maps.get("found"):
            maps_reviews = maps.get("review_count", 0)
            maps_rating  = maps.get("rating") or 0
            cs += min(20, maps_reviews // 5)   # up to 20 pts from Maps reviews
            if maps_rating >= 4.5:   cs += 10
            elif maps_rating >= 4.0: cs += 6
            elif maps_rating >= 3.5: cs += 3
        customer_success = min(100, cs)

        # ── Market Authority (0–100) ──────────────────────────────────────────
        # News + LinkedIn + Search + Maps presence
        ma = 20  # baseline
        if news.get("found"):
            ma += min(20, news.get("mention_count", 0) * 4)
        followers = linkedin.get("followers") or 0
        if followers > 0:
            ma += min(20, followers // 10000)
        if search.get("found"):
            ma += min(15, search.get("result_count_estimate", 0) // 10)
        if maps.get("found"):
            ma += 10   # being on Maps = local market presence confirmed
            maps_reviews = maps.get("review_count", 0)
            ma += min(10, maps_reviews // 10)
        market_authority = min(100, ma)

        # ── Social media bio bonus ────────────────────────────────────────
        # Social media was found by Playwright (not requests) so it often
        # has real data even when everything else is blocked
        social_media = fallback.get("social_media", {})
        social_found = []
        for platform, sm_data in (social_media or {}).items():
            if isinstance(sm_data, dict) and sm_data.get("url"):
                social_found.append(platform)
                # Having active social = market presence signal
                ma += 5
                if sm_data.get("bio"):
                    cs += 3   # bio = proof of customer-facing presence
        technical_depth  = min(100, technical_depth)
        customer_success = min(100, customer_success + (3 if social_found else 0))
        market_authority = min(100, market_authority)

        # ── general_content (service cards) bonus ─────────────────────────
        general_content = fallback.get("general_content", [])
        if general_content:
            gc_count = len(general_content)
            technical_depth  = min(100, technical_depth + min(20, gc_count * 4))
            customer_success = min(100, customer_success + min(15, gc_count * 3))
            market_authority = min(100, market_authority + min(10, gc_count * 2))

        # Track which sources were actually used
        sources_used = []
        if general_content:        sources_used.append(f"Homepage Services ({len(general_content)} cards)")
        if own_site.get("found"):  sources_used.append(f"Own Website ({len(own_site.get('pages_found',[]))} pages)")
        if maps.get("found"):      sources_used.append(f"Google Maps ({maps.get('review_count',0)} reviews)")
        if g2.get("found"):        sources_used.append("G2 Reviews")
        if news.get("found"):      sources_used.append("News Mentions")
        if linkedin.get("found"):  sources_used.append("LinkedIn")
        if search.get("found"):    sources_used.append("Search Engine")
        if social_found:           sources_used.append(f"Social Media ({', '.join(social_found)})")
        if not sources_used:       sources_used.append("Baseline only — no external signals found")

        print(f"[+] Fallback scores for '{company_name}': "
              f"TechDepth={technical_depth}, CustSuccess={customer_success}, "
              f"MktAuthority={market_authority} | Confidence={confidence.upper()}", file=sys.stderr)

        return {
            "technical_depth":  technical_depth,
            "customer_success": customer_success,
            "market_authority": market_authority,
            "confidence_level": confidence,
            "data_sources_used": sources_used,
            "fallback_used": True
        }