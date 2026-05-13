# 🤖 ScrapperAgent — Zoho Partner Strategic Intelligence

A high-performance competitive intelligence engine designed to scrape, analyze, and benchmark Zoho Partners. It combines **Playwright-driven deep extraction** with **Google Gemini 2.5 Flash Reasoning** to generate boardroom-ready executive reports and real-time performance indices.

---

## 🏗️ Project File Logic & Architecture

The system is built on a decoupled, modular framework that separates raw data orchestration from AI synthesis. Here is how each file functions and the logic it builds:

### 🌐 **`dashboard.py`** (The Strategic Hub)
*   **Work:** Serves as the web-based command center for the entire system.
*   **Logic:** Uses a Flask-based backend to bridge the Python scraping logic with a modern HTML/JS interface. It handles real-time status updates via AJAX, manages the "Is Competitor" mapping UI, and provides a direct visual link to generated PDF reports.

### 🎮 **`main.py`** (The Orchestration Core)
*   **Work:** The primary entry point for Command Line (CLI) operations.
*   **Logic:** It coordinates high-level workflows. It parses user arguments, initializes the browser session, and decides whether to perform a single scrape, a bulk sync, or a strategic report generation. It acts as the "glue" that connects the scraper to the analyzer and storage.

### 🧭 **`agent.py`** (The Navigator)
*   **Work:** Manages the browser lifecycle using Playwright.
*   **Logic:** It builds the "human-like" navigation patterns. It handles SSL certificate bypasses, manages timeouts, and performs intelligent link discovery (like finding social media links and clicking through Zoho profile tabs). It provides the platform for `extractors.py` to work on.

### 🕵️ **`extractors.py`** (The Deep Scraper Intelligence)
*   **Work:** Performs the actual data extraction and DOM analysis.
*   **Logic:** This is the most complex logic file. It uses keyword-based heuristics (`BLOG_URL_KW`, `CASE_TEXT_KW`) to distinguish between different types of content. It features a "cleaner" logic that strips away navigation bars, footers, and ads to extract only the high-value text from articles and case studies.

### 🧠 **`analyzer.py`** (The AI Brain)
*   **Work:** Translates raw data into strategic intelligence using LLMs (Google Gemini).
*   **Logic:** It builds the "Strategic Reasoning" layer. It takes the messy text from `extractors.py` and summarizes it into executive points. It also builds the logic for the **Competitive Benchmarking Matrix**, comparing multiple companies side-by-side to find market gaps.

### 📦 **`storage.py`** (The Insight Factory & Folder Logic)
*   **Work:** Handles data persistence, folder structures, and PDF generation.
*   **Logic:** 
    *   **Competitor Nesting:** Built-in logic to detect if a company is a "competitor" and automatically nest it inside its parent company's folder.
    *   **SPI Calculation:** Quantifies "Technical Depth" and "Customer Success" scores into numerical values.
    *   **PDF Rendering:** A complex rendering engine that uses `fpdf2` and `matplotlib` to build professional, dark-themed reports with dynamic charts.

### 📁 **`scraped_data/`** (The Database)
*   **Logic:** Automatically organized by company name. If a competitor is mapped, the logic inside `storage.py` ensures it is saved as: `scraped_data > [Parent_Company] > competitors > [Scraped_Company]`.

---

## 📖 Report Analysis Methodology

The ScrapperAgent doesn't just collect data; it synthesizes it using a structured analytical framework. Each section of the **Executive Strategic Report** is generated based on specific data points and AI reasoning:

| Report Section | Basis of Analysis | Analytical Framework |
| :--- | :--- | :--- |
| **1. Executive Summary** | Synthesis of all scraped content (Blogs, Case Studies, Overview). | Market Battle Framing: Identifies who is leading and why. |
| **2. Scoring Methodology** | Raw counts of high-value assets + AI content audit. | **Weighted Index**: Tech (30%), Proof (25%), Reach (20%), Trust (15%), Velocity (10%). |
| **3. Detailed Profile** | Deep-scrape of "About Us", "Services", and "Company Overview" tabs. | **Strategic Context**: Summarizes core competencies and brand positioning. |
| **4. GTM Strategy Comparison** | Analysis of service delivery models and lead generation signals. | **Comparative Analysis**: Channel strategy (Partners vs Direct), Inbound/Outbound, and Ecosystem Leverage. |
| **5. Competitive Cohort** | Mapping of all entities into strategic groups. | **Battle Narrative**: Framing the "war" (e.g., Specialization vs. Ecosystem Scale). |
| **6. Performance Index** | Cumulative calculation of Technical Depth, Success, and Reach. | **Cumulative Benchmarking**: Ranks partners against the baseline. |
| **7. Strategic Radar** | Intersection of technical capabilities (from case studies) and market reach. | **Capability Mapping**: Visualizes the "shape" of a company's market presence. |
| **8. Gap Analysis** | Delta calculation between baseline metrics and competitor leaders. | **Vulnerability Audit**: Quantifies where the baseline is losing "Market Friction". |
| **9. Strategic Roadmap** | Backwards-induction from identified gaps. | **Growth Modeling**: 12-month path (Q1-Q4) with specific milestones and tasks. |

---

## 🚀 Key Innovations

### 📊 Strategic Performance Index (SPI)
Unlike basic scrapers, ScrapperAgent quantifies market authority on a **0-100 scale** using a weighted multi-dimensional index:
-   **Technical Depth (40 pts)**: Analyzed through blog volume and content sophistication.
-   **Customer Success (45 pts)**: Measured by the density and quality of Case Studies/Customer Stories.
-   **Market Authority (15 pts)**: Based on social media footprint across LinkedIn, X, Instagram, and Facebook.

### 🌐 Intelligence Dashboard
A centralized web portal (`http://127.0.0.1:5000`) that allows leadership to:
-   **Bulk Sync**: Refresh the entire partner ecosystem database in one click.
-   **Real-time Progress**: Monitor scraping cycles with "Estimated Time Remaining" indicators.
-   **Report History**: Instant access to an archive of executive-level PDF reports.

### 🧠 Advanced Content Scoping
-   **CMS-Specific Extractors**: Specialized logic for Zoho Sites, WordPress (Elementor/Divi), and custom SPAs.
-   **AI-Driven Discovery**: Uses Google Gemini to "find" the Blog and Case Study listing pages even when links are hidden behind complex menus.
-   **Social Intelligence**: Bypasses login walls to capture brand voice and engagement snippets from social profiles.

---

## 🛠️ Setup & Deployment

### 1. Environment Configuration
Install the required engine components:
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Strategic API Access
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=AIzaSy...your-key-here
```

---

## 🕹️ Operations Guide

### Option A: The Intelligence Hub (Recommended)
Launch the web dashboard for a visual, automated experience:
```bash
python dashboard.py
```
> Access via browser at: `http://127.0.0.1:5000`

### Option B: The Command Line (Power Users)
Run targeted scrapes or bulk operations directly:
- **Targeted Scrape**: `python main.py --partner "Partner Name"`
- **Bulk Sync**: `python main.py --sync`
- **Generate Bulk Report**: `python main.py --bulk`

---

## 📁 Data Ecosystem
-   **`scraped_data/`**: Structured TXT and JSON archives for every scraped partner.
-   **`trigya report/`**: The "Gold" folder containing the final **Executive Competitive Intelligence PDFs**.
-   **`partner_collections/`**: Managed lists of partners to be processed during sync cycles.

---

## 📡 External API Synchronization

ScrapperAgent can automatically push its intelligence to your own remote database or custom API in real-time.

### 1. Configuration
To enable API sync, add your endpoint to the `.env` file:
```env
API_WEBHOOK_URL=https://your-api-endpoint.com/v1/receive-data
```

### 2. The JSON Payload
When a scrape completes, the system performs a `POST` request to your URL with the following JSON structure:

```json
{
  "partner_id": "ext_9bef40659b58",
  "name": "Accenture",
  "website": "https://www.accenture.com",
  "relationship": {
    "type": "competitor",
    "parent_company": "Wipro",
    "folder_path": "Wipro/competitors/Accenture"
  },
  "overview": "Company description and mission...",
  "blogs": [
    { "title": "AI in 2026", "link": "...", "content": "..." }
  ],
  "case_studies": [],
  "customer_stories": [],
  "social_media": { "linkedin": "...", "twitter": "..." }
}
```

### 3. 🔄 Circular Hierarchy Logic (360° Analysis)
The system features a **Relationship-Aware Discovery Engine**. This means:
*   **Logical Nesting**: The `relationship` tag tells your API exactly where the company sits in the ecosystem (Parent vs. Competitor).
*   **Bi-Directional Reports**: 
    *   Selecting a **Parent** (Wipro) pulls all its competitors into the report.
    *   Selecting a **Competitor** (Accenture) automatically pulls its **Parent** (Wipro) AND its **Peers** (other siblings) into the report.
*   **Result**: You get a complete 360° market view regardless of which company you start your analysis with.

---

## 🛡️ Secure Trigger API (Incoming)

You can trigger a scrape session remotely from any external system (like a CRM or a custom dashboard).

### 1. Endpoint
**URL**: `http://[YOUR_IP]:5000/api/trigger-scrape`  
**Method**: `POST`  
**Header**: `X-API-Key: [Your SCRAPER_API_KEY from .env]`

### 2. Request Body (JSON)
```json
{
  "partner_name": "Accenture",
  "parent_company": "Wipro"
}
```

### 3. Example (cURL)
```bash
curl -X POST http://127.0.0.1:5000/api/trigger-scrape \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your_secret_key" \
     -d '{"partner_name": "Accenture", "parent_company": "Wipro"}'
```

### 3. Trigger Competitive Report
**URL**: `http://[YOUR_IP]:5000/api/trigger-report`  
**Method**: `POST`  
**Header**: `X-API-Key: [Your REPORT_API_KEY from .env]`

**Request Body (JSON)**:
```json
{
  "baseline_company": "Rotabull"
}
```

### 4. Check Task Status (IMPORTANT)
Triggering an API task returns a `202 Accepted` status with `"status": "RUNNING"`. This indicates the task has **started**. To check if a task is finished, poll the Status API.

**URL**: `http://[YOUR_IP]:5000/api/status/[report|scrape|sync]`  
**Method**: `GET`  
**Header**: `X-API-Key: [Your relevant API_KEY from .env]`

**Success Response (JSON)**:
```json
{
  "status": "completed",
  "message": "Task finished successfully."
}
```

---

## 📝 Performance & Reliability
-   **Resilience**: Automated SSL bypass and headless execution ensure 24/7 reliability.
-   **Intelligence**: AI-driven summarization automatically translates and cleans non-english or "noisy" website content.
-   **Visual Excellence**: PDFs feature custom navy/gold branding, card-based layouts, and Matplotlib-driven market benchmarks.
