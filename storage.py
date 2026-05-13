import os
import re
import sys

# Ensure bundled dependencies in temp_libs are accessible
temp_libs_path = os.path.join(os.path.dirname(__file__), "temp_libs")
if os.path.exists(temp_libs_path) and temp_libs_path not in sys.path:
    sys.path.insert(0, temp_libs_path)

import json
import requests
import time
from fpdf import FPDF
from fpdf.fonts import FontFace
import matplotlib.pyplot as plt # pyrefly: ignore [missing-import] # type: ignore
import numpy as np # pyrefly: ignore [missing-import] # type: ignore
try:
    from matplotlib.patches import Patch # pyrefly: ignore [missing-import] # type: ignore
except ImportError:
    Patch = None
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from catalyst_client import catalyst_client

def clean_text(text):
    """Sanitizes text for FPDF latin-1 encoding."""
    if not isinstance(text, str): return str(text)
    replacements = {
        '\u2013': '-', # en dash
        '\u2014': '-', # em dash
        '\u2018': "'", # left single quote
        '\u2019': "'", # right single quote
        '\u201c': '"', # left double quote
        '\u201d': '"', # right double quote
        '\u2022': '*', # bullet point
        '\u2026': '...', # ellipsis
        '\u2122': '(TM)', # trademark
        '\u00ae': '(R)', # registered
        '\u00a9': '(C)', # copyright
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    # Final fallback for other non-latin1 characters
    return text.encode('latin-1', 'replace').decode('latin-1')

def clean_filename(name):
    """
    Consistently cleans a company name to be used in a filename or folder.
    Removes protocols, www, and common extensions (.com, .in, etc.).
    """
    if not name: return "Unknown"
    # 1. Lowercase for processing
    name = name.lower()
    # 2. Remove protocol
    name = re.sub(r'^https?://', '', name)
    # 3. Remove www.
    name = re.sub(r'^www\.', '', name)
    # 4. Remove common extensions
    for suffix in ['.com', '.co.in', '.in', '.org', '.net', '.co', '.io', '.ai']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    # 5. Remove generic prefixes
    name = re.sub(r'^premium zoho partner in ', '', name)
    # 6. Sanitize characters - allow only alpha-numeric
    name = re.sub(r'[^a-z0-9]', ' ', name).strip()
    # 7. Title case and join with underscores
    name = "_".join([w.capitalize() for w in name.split()])
    return name or "Unknown"

def format_content_for_txt(text, indent="      ", width=80):
    """Cleans up scraped content for TXT files: removes extra newlines and wraps text."""
    if not text: return "(no content)"
    # Remove excessive newlines
    text = re.sub(r'\n\s*\n', '\n\n', text)
    lines = []
    for paragraph in text.split('\n\n'):
        paragraph = re.sub(r'\s+', ' ', paragraph).strip()
        if not paragraph: continue
        
        # Simple word wrap
        words = paragraph.split(' ')
        current_line = []
        current_len = 0
        for word in words:
            if current_len + len(word) + 1 > width:
                lines.append(indent + " ".join(current_line))
                current_line = [word]
                current_len = len(word)
            else:
                current_line.append(word)
                current_len += len(word) + 1
        if current_line:
            lines.append(indent + " ".join(current_line))
        lines.append("") # paragraph break
    
    return "\n".join(lines).strip()

# =========================
# PDF CLASS
# =========================
class ReportPDF(FPDF):

    def __init__(self, partner_name="BASE ENTITY", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.partner_name = partner_name.upper()

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(120,120,120)
            self.cell(0, 5, f"{self.partner_name} | STRATEGIC COMPETITIVE INTELLIGENCE", 0, 1, "R")

    def section_title(self, title):
        title = clean_text(title)
        self.ln(5)
        self.set_fill_color(13, 71, 161)
        self.set_text_color(255,255,255)
        self.set_font("Helvetica","B",14)
        self.cell(0,10,title,0,1,"L",True)
        self.ln(5)

    def body_text(self, text):
        text = clean_text(text)
        self.set_text_color(33,37,41)
        self.set_font("Helvetica","",11)
        self.multi_cell(0, 6, text, align='J')
        self.ln(5)


# =========================
# COVER PAGE
# =========================
def add_cover(pdf, partner_name):
    pdf.add_page()

    pdf.set_fill_color(13,71,161)
    pdf.rect(0,0,210,160,"F")

    pdf.set_text_color(255,255,255)
    pdf.set_font("Helvetica","B",32)
    pdf.set_y(60)
    pdf.cell(0,15,"STRATEGIC MARKET",0,1,"C")
    pdf.cell(0,15,"INTELLIGENCE",0,1,"C")

    pdf.set_font("Helvetica","",14)
    pdf.cell(0,10,f"{partner_name} vs Analysis",0,1,"C")

    pdf.set_y(200)
    pdf.set_text_color(0,0,0)
    pdf.set_font("Helvetica","B",24)
    pdf.cell(0,10,partner_name.upper(),0,1,"C")


# =========================
# CHARTS
# =========================

def _apply_dark_base(fig, ax):
    """Apply shared dark intelligence-dashboard styling to any axes."""
    BG       = '#0D1117'
    PANEL    = '#161B22'
    GRID     = '#21262D'
    TEXT     = '#E6EDF3'
    SUBTEXT  = '#8B949E'

    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    ax.tick_params(colors=SUBTEXT, labelsize=9)
    ax.xaxis.label.set_color(SUBTEXT)
    ax.yaxis.label.set_color(SUBTEXT)

    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)

    ax.grid(axis='x', color=GRID, linewidth=0.6, linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)

    return BG, PANEL, GRID, TEXT, SUBTEXT


def chart_revenue_trajectory(trajectory_data):
    """Generates a line chart for revenue growth over time."""
    if not trajectory_data: return
    
    years    = [y for y in trajectory_data.get("years", ["FY2021", "FY2022", "FY2023", "FY2024"]) if y is not None]
    datasets = trajectory_data.get("data", [])
    if not years or not datasets:
        print("[*] chart_revenue_trajectory: no valid years or datasets — skipping chart.", file=sys.stderr)
        return
    
    BG = '#FFFFFF'
    AXIS = '#333333'
    GRID = '#EEEEEE'
    COLORS = ['#0D47A1', '#00ACC1', '#FF9800', '#4CAF50', '#9C27B0']
    
    # Handle "All Zeros" scenario for better visual spacing
    all_vals = []
    for entry in datasets:
        all_vals.extend([v for v in entry.get("values", []) if v is not None])
    
    is_all_zero = all(float(v) == 0 for v in all_vals) if all_vals else True
    
    plt.figure(figsize=(9.5, 4))
    plt.gca().set_facecolor(BG)
    
    label_positions = {}

    for i, entry in enumerate(datasets):
        name = entry.get("name", "Company")
        values = entry.get("values", [])
        color = COLORS[i % len(COLORS)]
        
        clean_pairs = [(yr, v) for yr, v in zip(years, values) if v is not None]
        clean_years  = [p[0] for p in clean_pairs]
        clean_values = [p[1] for p in clean_pairs]

        if not clean_values:
            continue

        plt.plot(clean_years, clean_values, marker='o', label=name, color=color, linewidth=2.0, markersize=6)

        for x, y in zip(clean_years, clean_values):
            try:
                y_val = float(y)
                pos_key = f"{x}_{round(y_val, 2)}"
                
                # COLLISION AVOIDANCE: Only show one label per point if values are identical (zeros)
                if pos_key in label_positions:
                    continue 
                label_positions[pos_key] = True

                offset = 0.12 if not is_all_zero else 0.4
                plt.text(x, y_val + offset, f"${y_val:.1f}B", ha='center', va='bottom', 
                         fontsize=7, color=color, fontweight='bold')
            except (TypeError, ValueError):
                pass

    if is_all_zero:
        plt.ylim(-1, 5) # Provide breathing room if no data found

    plt.title("Revenue Growth Trajectory FY2021-FY2024", fontsize=10, fontweight='bold', pad=15)
    plt.ylabel("Revenue (USD B)", fontsize=8)
    
    # LEGEND FIX: Move legend to the side to prevent overlapping data points
    plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=7, frameon=True, borderpad=1)
    
    plt.grid(True, axis='y', linestyle='--', alpha=0.4, color=GRID)
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    
    plt.tight_layout(rect=[0, 0, 0.82, 1]) # Make room for legend
    plt.savefig("revenue_trajectory.png", dpi=180)
    plt.close()

def chart_workforce_size(workforce_data):
    """Generates a horizontal bar chart for workforce size."""
    if not workforce_data: return
    
    # Clean and validate workforce data
    cleaned_workforce = []
    for d in workforce_data:
        count = d.get("count")
        if count is None:
            continue
        try:
            # Ensure it's a number
            d["count"] = float(str(count).replace(',', '').replace(' ', ''))
            cleaned_workforce.append(d)
        except (ValueError, TypeError):
            continue
            
    if not cleaned_workforce:
        print("[*] chart_workforce_size: no valid counts found — skipping chart.", file=sys.stderr)
        return

    # Sort by count for better visualization
    cleaned_workforce = sorted(cleaned_workforce, key=lambda x: x.get('count', 0))
    
    names = [d.get("name", "Company") for d in cleaned_workforce]
    counts = [d.get("count", 0) for d in cleaned_workforce]
    
    BG = '#FFFFFF'
    AXIS = '#333333'
    GRID = '#EEEEEE'
    # Match colors in image: Cognizant (Blue), Capgemini (Teal), LTIMindtree (Orange)
    COLOR_MAP = {
        "Cognizant": "#0D47A1",
        "Capgemini": "#00ACC1",
        "LTIMindtree": "#FF9800",
        "Lti": "#FF9800",
        "Mindtree": "#FF9800"
    }
    
    colors = [COLOR_MAP.get(n, '#4CAF50') for n in names]
    
    plt.figure(figsize=(9, 3.5))
    plt.gca().set_facecolor(BG)
    
    bars = plt.barh(names, counts, color=colors, height=0.5)
    
    max_c = max(counts) if counts else 1
    for bar in bars:
        width = bar.get_width()
        plt.text(width + (max_c * 0.02), bar.get_y() + bar.get_height()/2, f"{int(width/1000)}K", 
                 va='center', fontsize=8, fontweight='bold')

    plt.title("Workforce Size — FY2024", fontsize=10, fontweight='bold', pad=15)
    plt.xlabel("Employees (Thousands)", fontsize=8)
    plt.grid(True, axis='x', linestyle='--', alpha=0.5, color=GRID)
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    
    plt.tight_layout()
    plt.savefig("workforce_size.png", dpi=180)
    plt.close()

def chart_performance(partners, baseline_name):
    # ── FILTERING (Top 10 + Baseline) ─────────────────────────────────────────
    def get_total_score(p):
        s = p.get("scores", {}).values()
        total = 0
        for v in s:
            try: total += float(v)
            except: pass
        return total

    # Sort all by total score
    sorted_p = sorted(partners, key=get_total_score, reverse=True)
    
    # Get top 10 and ensure baseline is included
    top_10 = sorted_p[:10]
    baseline = next((p for p in partners if p["name"] == baseline_name), None)
    
    display_partners = top_10
    if baseline and baseline not in top_10:
        display_partners.append(baseline)
    
    # Re-sort display partners so the chart stays ordered
    display_partners = sorted(display_partners, key=get_total_score, reverse=True)
    
    # Use filtered list for chart
    names      = [p["name"] for p in display_partners]
    confidence = [p.get("confidence_level", "high") for p in display_partners]
    fallbacks  = [p.get("fallback_used", False) for p in display_partners]
    tech, success, authority = [], [], []
    for p in display_partners:
        s = p.get("scores", {})
        try: tech.append(float(s.get("technical_depth", 0)))
        except: tech.append(0.0)
        try: success.append(float(s.get("customer_success", 0)))
        except: success.append(0.0)
        try: authority.append(float(s.get("market_authority", 0)))
        except: authority.append(0.0)

    # ── PALETTE ───────────────────────────────────────────────────────────────
    C_TECH    = '#58A6FF'   # cool blue
    C_SUCCESS = '#F0B429'   # amber
    C_AUTH    = '#3FB950'   # green
    C_BASE    = '#FF7B54'   # baseline highlight
    BG        = '#0D1117'
    PANEL     = '#161B22'
    GRID      = '#21262D'
    TEXT      = '#E6EDF3'
    SUBTEXT   = '#8B949E'

    # Confidence badge colours
    CONF_COLORS = {
        "high":         "#3FB950",   # green
        "medium":       "#F0B429",   # amber
        "low":          "#FF7B54",   # orange
        "insufficient": "#F85149",   # red
    }

    height = max(0.55, min(0.85, 10 / max(len(names), 1)))
    fig, ax = plt.subplots(figsize=(13, max(6, len(names) * 0.65 + 2)))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    y_pos = range(len(names))
    bars_t = ax.barh(y_pos, tech,      height=height, label="Technical Depth",  color=C_TECH,    alpha=0.92)
    bars_s = ax.barh(y_pos, success,   height=height, left=tech,
                     label="Customer Success", color=C_SUCCESS, alpha=0.92)
    bars_a = ax.barh(y_pos, authority, height=height,
                     left=[t + s for t, s in zip(tech, success)],
                     label="Market Authority", color=C_AUTH, alpha=0.92)

    # Rounded end caps (thin white overlay on rightmost bar)
    totals = [t + s + a for t, s, a in zip(tech, success, authority)]
    for i, total in enumerate(totals):
        ax.barh(i, 2, height=height * 0.6, left=total - 1, color='white', alpha=0.15)

    # Value labels at end of each stacked bar
    for i, total in enumerate(totals):
        ax.text(total + 1.5, i, f'{int(total)}',
                va='center', ha='left', fontsize=8.5,
                color=TEXT, fontweight='bold')

    # ── CONFIDENCE BADGES ─────────────────────────────────────────────────────
    # Draw a small coloured dot + label to the right of the score
    max_total = max(totals) if totals else 300
    badge_x   = max_total + 18  # position badges past the score label
    for i, (conf, is_fallback) in enumerate(zip(confidence, fallbacks)):
        badge_color = CONF_COLORS.get(conf, SUBTEXT)
        # Dot
        ax.plot(badge_x, i, 'o', color=badge_color, markersize=5, zorder=6)
        # Label
        label = conf.upper()
        if is_fallback:
            label += " *"   # asterisk = external data used
        ax.text(badge_x + 2, i, label,
                va='center', ha='left', fontsize=7,
                color=badge_color, fontweight='bold')

    # Y-axis labels — highlight baseline
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(names, fontsize=9)
    for tick, name in zip(ax.get_yticklabels(), names):
        if name.strip().lower() == baseline_name.strip().lower():
            tick.set_color(C_BASE)
            tick.set_fontweight('bold')
            tick.set_fontsize(10.5)
            row_idx = names.index(name)
            ax.axhspan(row_idx - height / 2, row_idx + height / 2,
                       color=C_BASE, alpha=0.07, zorder=0)
        else:
            tick.set_color(SUBTEXT)

    # Axes styling
    ax.tick_params(axis='x', colors=SUBTEXT, labelsize=8.5)
    ax.set_xlabel("Cumulative Strategic Score (0–300)", color=SUBTEXT, fontsize=9.5, labelpad=8)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.grid(axis='x', color=GRID, linewidth=0.5, linestyle='--', alpha=0.6)
    ax.set_axisbelow(True)
    ax.invert_yaxis()

    # Extend x-axis to make room for badges
    ax.set_xlim(right=badge_x + 28)

    # Legend — dark card style
    legend = ax.legend(loc='lower right', fontsize=8.5, framealpha=0.0,
                       labelcolor=TEXT, borderpad=0.8)
    for patch in legend.get_patches():
        patch.set_alpha(0.9)

    # Title block
    fig.text(0.02, 0.97,
             f"MARKET PERFORMANCE INDEX",
             color=TEXT, fontsize=14, fontweight='bold',
             va='top', ha='left')
    fig.text(0.02, 0.93,
             f"{baseline_name.upper()} COMPETITIVE BENCHMARKING",
             color=SUBTEXT, fontsize=9, va='top', ha='left')

    # Confidence legend footnote
    fig.text(0.02, 0.02,
             "Confidence:  GREEN = High (own-site data)   AMBER = Medium   ORANGE = Low   RED = Insufficient   * = External signals used",
             color=SUBTEXT, fontsize=7, va='bottom', ha='left')

    # Thin top accent line
    fig.add_artist(plt.Line2D([0.02, 0.98], [0.99, 0.99],
                              transform=fig.transFigure,
                              color=C_TECH, linewidth=1.5, alpha=0.8))

    plt.tight_layout(rect=[0, 0.04, 1, 0.92])
    plt.savefig("performance.png", dpi=180, facecolor=BG)
    plt.close()


def chart_distribution(partners, baseline_name, baseline_score):
    # ── DATA (unchanged) ──────────────────────────────────────────────────────
    all_scores = []
    for p in partners:
        s = p.get("scores", {}).values()
        total = 0
        for v in s:
            try: total += float(v)
            except: pass
        all_scores.append(total)

    # ── PALETTE ───────────────────────────────────────────────────────────────
    BG      = '#0D1117'
    PANEL   = '#161B22'
    GRID    = '#21262D'
    TEXT    = '#E6EDF3'
    SUBTEXT = '#8B949E'
    C_BAR   = '#1F6FEB'
    C_BASE  = '#FF7B54'

    fig, ax = plt.subplots(figsize=(11, 6))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    # Histogram with gradient-like stacking
    n, bins, patches = ax.hist(all_scores, bins=12,
                                color=C_BAR, alpha=0.75,
                                edgecolor=BG, linewidth=0.8,
                                label="Partner Density")

    # Colour bars by proximity to baseline (warmer = closer)
    for patch, left in zip(patches, bins[:-1]):
        dist = abs((left + (bins[1] - bins[0]) / 2) - baseline_score)
        alpha = max(0.35, 1 - dist / (max(bins) - min(bins) + 1))
        patch.set_alpha(alpha)

    # Baseline vertical line
    ax.axvline(baseline_score, color=C_BASE, linestyle='--',
               linewidth=2.2, label=f"{baseline_name} Position", zorder=5)

    # Filled area under baseline
    ax.axvspan(baseline_score - 5, baseline_score + 5,
               color=C_BASE, alpha=0.08, zorder=1)

    # Annotation callout
    ymax = max(n)
    ax.annotate(
        f" {baseline_name.upper()}\n SCORE: {int(baseline_score)}",
        xy=(baseline_score, ymax * 0.68),
        xytext=(baseline_score + max(bins) * 0.07, ymax * 0.82),
        arrowprops=dict(arrowstyle='->', color=C_BASE,
                        lw=1.8, connectionstyle='arc3,rad=0.2'),
        color=C_BASE, fontweight='bold', fontsize=9,
        bbox=dict(boxstyle='round,pad=0.4', fc=PANEL, ec=C_BASE, lw=1.2)
    )

    # Axes styling
    ax.tick_params(colors=SUBTEXT, labelsize=8.5)
    ax.set_xlabel("Strategic Score (0–300)", color=SUBTEXT, fontsize=9.5, labelpad=8)
    ax.set_ylabel("Number of Partners",      color=SUBTEXT, fontsize=9.5, labelpad=8)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.grid(color=GRID, linewidth=0.5, linestyle='--', alpha=0.5)
    ax.set_axisbelow(True)

    legend = ax.legend(fontsize=8.5, framealpha=0, labelcolor=TEXT)

    # Title block
    fig.text(0.02, 0.97, "COHORT DISTRIBUTION",
             color=TEXT, fontsize=13, fontweight='bold', va='top')
    fig.text(0.02, 0.93, "MARKET AUTHORITY INDEX — PARTNER DENSITY CURVE",
             color=SUBTEXT, fontsize=8.5, va='top')
    fig.add_artist(plt.Line2D([0.02, 0.98], [0.99, 0.99],
                              transform=fig.transFigure,
                              color=C_BAR, linewidth=1.5, alpha=0.8))

    plt.tight_layout(rect=[0, 0, 1, 0.91])
    plt.savefig("distribution.png", dpi=180, facecolor=BG)
    plt.close()


def radar_chart(scores):
    # ── DATA (unchanged) ──────────────────────────────────────────────────────
    labels = [l.replace('_', ' ').title() for l in scores.keys()]
    values = []
    for v in scores.values():
        try: values.append(float(v))
        except: values.append(0.0)
    
    values += values[:1]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]

    # ── PALETTE ───────────────────────────────────────────────────────────────
    BG      = '#0D1117'
    PANEL   = '#0D1117'
    GRID    = '#21262D'
    TEXT    = '#E6EDF3'
    SUBTEXT = '#8B949E'
    C_LINE  = '#58A6FF'
    C_FILL  = '#1F6FEB'
    C_MARK  = '#FF7B54'

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    # Concentric reference rings
    max_val = max(values[:-1]) if values[:-1] else 100
    for r_frac in [0.25, 0.5, 0.75, 1.0]:
        ring_vals = [max_val * r_frac] * (len(angles))
        ax.plot(angles, ring_vals, color=GRID, linewidth=0.7, linestyle='--', zorder=1)

    # Spoke gridlines
    for angle in angles[:-1]:
        ax.plot([angle, angle], [0, max_val], color=GRID, linewidth=0.7, zorder=1)

    # Filled area with gradient effect (two overlapping fills)
    ax.fill(angles, values, color=C_FILL, alpha=0.18, zorder=2)
    ax.fill(angles, [v * 0.6 for v in values], color=C_FILL, alpha=0.12, zorder=2)

    # Main polygon line
    ax.plot(angles, values, color=C_LINE, linewidth=2.2, zorder=3)

    # Data point markers
    ax.scatter(angles[:-1], values[:-1],
               color=C_MARK, s=55, zorder=4, edgecolors=BG, linewidths=1.5)

    # Value labels at each vertex
    for angle, value in zip(angles[:-1], values[:-1]):
        ax.text(angle, value + max_val * 0.08, f'{int(value)}',
                ha='center', va='center',
                color=TEXT, fontsize=8.5, fontweight='bold', zorder=5)

    # Axis labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9, fontweight='bold', color=TEXT)
    ax.set_yticklabels([])
    
    # Ensure we don't crash on zero max_val
    plot_max = max_val * 1.25 if max_val > 0 else 100
    ax.set_ylim(0, plot_max)
    ax.spines['polar'].set_edgecolor(GRID)
    ax.tick_params(pad=12)

    # Title
    fig.text(0.5, 0.97, "STRATEGIC PERFORMANCE RADAR",
             color=TEXT, fontsize=11, fontweight='bold',
             ha='center', va='top')
    fig.add_artist(plt.Line2D([0.15, 0.85], [0.985, 0.985],
                              transform=fig.transFigure,
                              color=C_LINE, linewidth=1.2, alpha=0.7))

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig("radar.png", dpi=180, bbox_inches='tight', facecolor=BG)
    plt.close()


def gap_chart(gap):
    labels = [str(l).replace('_', ' ') for l in gap.keys()]
    values = []
    for v in gap.values():
        try: values.append(float(v))
        except: values.append(0.0)

    BG       = '#0D1117'
    PANEL    = '#161B22'
    GRID     = '#21262D'
    TEXT     = '#E6EDF3'
    SUBTEXT  = '#8B949E'
    C_POS    = '#3FB950'
    C_NEG    = '#F85149'
    C_ZERO   = '#8B949E'

    # More compact figsize
    fig, ax = plt.subplots(figsize=(9.5, max(4, len(labels) * 0.6 + 1.8)))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    colors = [C_POS if v >= 0 else C_NEG for v in values]
    bars   = ax.barh(labels, values, color=colors, alpha=0.88,
                     height=0.45, edgecolor=BG, linewidth=0.5)

    ax.axvline(0, color=C_ZERO, linewidth=1.2, zorder=5)

    for i, (bar, val) in enumerate(zip(bars, values)):
        if i % 2 == 0:
            ax.axhspan(i - 0.4, i + 0.4, color='white', alpha=0.015, zorder=0)
        
        w = bar.get_width()
        cy = bar.get_y() + bar.get_height() / 2
        
        # SMART OFFSET: If bar is very short, move label further away from Y-axis
        if abs(w) < 5:
            offset = 4 if w >= 0 else -4
        else:
            offset = 1.8 if w >= 0 else -1.8
            
        ax.text(w + offset, cy, f'{"+" if w > 0 else ""}{int(w)}%',
                va='center', ha='left' if w >= 0 else 'right', 
                fontsize=8, fontweight='bold', color=C_POS if w >= 0 else C_NEG)

    # Increased pad to avoid collision between labels and bars
    ax.tick_params(axis='y', colors=TEXT, labelsize=8.5, pad=15)
    ax.tick_params(axis='x', colors=SUBTEXT, labelsize=8)
    ax.set_xlabel("Percentage Variance (%)", color=SUBTEXT, fontsize=8.5, labelpad=8)
    
    # DYNAMIC X-LIMITS: Ensure room for labels even if values are small
    xmin, xmax = ax.get_xlim()
    ax.set_xlim(min(xmin, -25), max(xmax, 15))

    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.grid(axis='x', color=GRID, linewidth=0.4, linestyle='--', alpha=0.4)
    ax.set_axisbelow(True)

    try:
        if Patch is not None:
            legend_elements = [
                Patch(facecolor=C_POS, label='Above Market', alpha=0.8),
                Patch(facecolor=C_NEG, label='Below Market',  alpha=0.8),
            ]
            ax.legend(handles=legend_elements, fontsize=7.5, framealpha=0, labelcolor=TEXT, loc='lower right')
        else:
            raise ImportError("Patch not found")
    except Exception as e:
        print(f"[*] Warning: Gap chart legend failed ({e}). Using standard legend.")
        ax.legend(['Above Market', 'Below Market'], fontsize=7.5, framealpha=0, labelcolor=TEXT, loc='lower right')

    fig.text(0.02, 0.96, "COMPETITIVE GAP ANALYSIS", color=TEXT, fontsize=12, fontweight='bold', va='top')
    
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    # Adjusted left margin based on content
    plt.subplots_adjust(left=0.38) 
    plt.savefig("gap.png", dpi=180, facecolor=BG)
    plt.close()


def authority_chart(data):
    # ── DATA (unchanged) ──────────────────────────────────────────────────────
    labels = [f"{l.replace('_', ' ').title()} ({int(float(v)) if str(v).replace('.','',1).isdigit() else 0})" for l, v in data.items()]
    values = []
    for v in data.values():
        try: values.append(float(v))
        except: values.append(0.0)

    # ── PALETTE ───────────────────────────────────────────────────────────────
    BG      = '#0D1117'
    TEXT    = '#E6EDF3'
    SUBTEXT = '#8B949E'
    COLORS  = ['#58A6FF', '#F0B429', '#3FB950', '#F85149', '#BC8CFF']

    fig, ax = plt.subplots(figsize=(7, 7))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,          # we'll draw a custom legend instead
        autopct='%1.1f%%',
        colors=COLORS,
        startangle=140,
        pctdistance=0.78,
        wedgeprops=dict(linewidth=2.5, edgecolor=BG),
    )

    # Percentage text styling
    plt.setp(autotexts, size=9.5, weight='bold', color='white')

    # Donut hole with inner label
    centre = plt.Circle((0, 0), 0.58, fc=BG)
    fig.gca().add_artist(centre)
    ax.text(0, 0.08, 'CAPABILITY', ha='center', va='center',
            color=SUBTEXT, fontsize=8, fontweight='bold')
    ax.text(0, -0.08, 'BALANCE', ha='center', va='center',
            color=SUBTEXT, fontsize=8, fontweight='bold')

    try:
        if Patch is not None:
            legend_patches = [
                Patch(facecolor=COLORS[i % len(COLORS)], label=labels[i], linewidth=0)
                for i in range(len(labels))
            ]
            leg = ax.legend(
                handles=legend_patches,
                loc='lower center',
                bbox_to_anchor=(0.5, -0.18),
                ncol=2,
                fontsize=8.2,
                framealpha=0,
                labelcolor=TEXT,
                handlelength=1.2,
                handleheight=1.0,
                borderpad=0.5,
            )
        else:
            raise ImportError("Patch not found")
    except Exception as e:
        print(f"[*] Warning: Custom legend failed ({e}). Using standard legend.")
        ax.legend(labels, loc='lower center', bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=8.2)

    plt.axis('equal')

    # Title block
    fig.text(0.5, 0.97, "STRATEGIC CAPABILITY BALANCE",
             color=TEXT, fontsize=11, fontweight='bold',
             ha='center', va='top')
    fig.add_artist(plt.Line2D([0.15, 0.85], [0.985, 0.985],
                              transform=fig.transFigure,
                              color=COLORS[0], linewidth=1.2, alpha=0.7))

    plt.tight_layout(rect=[0, 0.1, 1, 0.94])
    plt.savefig("authority.png", dpi=180, bbox_inches='tight', facecolor=BG)
    plt.close()


def chart_solutions(benchmarking_data, baseline_name):
    """Visualizes product-specific efficiency vs challenges."""
    if not benchmarking_data: return
    
    # Prep data — support both old and new key names
    data = benchmarking_data # Remove the [:12] limit to show all products
    products = [d.get('solution_identified', d.get('product_name', 'Solution')) for d in data]
    partners = [d.get('partner_name', 'Partner') for d in data]
    industries = [d.get('target_vertical', d.get('target_industry', 'Multi')) for d in data]
    
    efficiency = []
    for d in data:
        try: efficiency.append(float(d.get('efficiency_score', 0)))
        except: efficiency.append(0.0)
        
    challenges = []
    for d in data:
        try: challenges.append(float(d.get('complexity_score', d.get('challenge_score', 0))))
        except: challenges.append(0.0)

    # ── PALETTE ───────────────────────────────────────────────────────────────
    BG      = '#0D1117'
    PANEL   = '#161B22'
    GRID    = '#21262D'
    TEXT    = '#E6EDF3'
    SUBTEXT = '#8B949E'
    C_EFF   = '#3FB950'
    C_CHA   = '#F85149'
    C_BASE  = '#FF7B54'

    fig, ax = plt.subplots(figsize=(12, max(6, len(data) * 0.75 + 2)))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    y = np.arange(len(data))
    height = 0.35

    ax.barh(y - height/2, efficiency, height, label='Solution Efficiency', color=C_EFF, alpha=0.88)
    ax.barh(y + height/2, challenges, height, label='Technical Challenges', color=C_CHA, alpha=0.88)

    # Labels with Industry context
    y_labels = [f"{prod}\n({part}) | {ind}" for prod, part, ind in zip(products, partners, industries)]
    ax.set_yticks(y)
    ax.set_yticklabels(y_labels, fontsize=8.5, color=SUBTEXT)
    
    # Highlight baseline
    for i, label in enumerate(ax.get_yticklabels()):
        if baseline_name.lower() in partners[i].lower() or baseline_name.lower() in products[i].lower():
            label.set_color(C_BASE)
            label.set_fontweight('bold')
            label.set_fontsize(9.5)

    ax.tick_params(colors=SUBTEXT, labelsize=8.5)
    ax.set_xlabel("Maturity & Complexity Score (0–100)", color=SUBTEXT, fontsize=9.5)
    for spine in ax.spines.values(): spine.set_edgecolor(GRID)
    ax.grid(axis='x', color=GRID, linestyle='--', alpha=0.45)
    ax.invert_yaxis()
    
    ax.legend(loc='upper right', fontsize=8.5, framealpha=0, labelcolor=TEXT)

    fig.text(0.02, 0.97, "PRODUCT & SOLUTION BENCHMARKING", color=TEXT, fontsize=14, fontweight='bold', va='top')
    fig.text(0.02, 0.93, "COMPARATIVE ANALYSIS OF EFFICIENCY VS IMPLEMENTATION CHALLENGES", color=SUBTEXT, fontsize=9, va='top')
    
    plt.tight_layout(rect=[0, 0, 1, 0.92])
    plt.savefig("solutions.png", dpi=180, facecolor=BG)
    plt.close()


# =========================
# MAIN REPORT FUNCTION
# =========================

def generate_report(data, filename="final_report.pdf"):
    # Determine the baseline name dynamically
    baseline_name = data["partners"][0]["name"] if (data.get("partners") and len(data["partners"]) > 0) else "Strategy Report"
    
    pdf = ReportPDF(partner_name=baseline_name)

    # 1 COVER
    add_cover(pdf, baseline_name)
    print(f"[*] PDF: Rendered Cover Page")

    # 2 EXECUTIVE SUMMARY
    pdf.add_page()
    pdf.section_title("EXECUTIVE SUMMARY")
    pdf.body_text(data.get("executive_summary", "Strategic summary pending."))
    print(f"[*] PDF: Rendered Executive Summary")

    # 3 SCORING METHODOLOGY (New Section)
    if data.get("scoring_methodology"):
        pdf.add_page()
        pdf.section_title("SCORING METHODOLOGY & FORMULA")
        pdf.body_text(data["scoring_methodology"])

    # 4 DETAILED BASELINE PROFILE
    pdf.add_page()
    pdf.section_title(f"DETAILED PROFILE: {baseline_name}")
    
    baseline_info = data["partners"][0] if data.get("partners") else {}
    if baseline_info.get("overview"):
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(13, 71, 161)
        pdf.cell(0, 10, "STRATEGIC OVERVIEW", 0, 1)
        pdf.body_text(baseline_info["overview"])
    print(f"[*] PDF: Rendered Baseline Profile")
    
    # 4. GTM STRATEGY ANALYSIS
    if data.get("gtm_strategy_analysis"):
        pdf.add_page()
        pdf.section_title("4. GO-TO-MARKET (GTM) STRATEGY COMPARISON")
        gtm = data["gtm_strategy_analysis"]
        pdf.body_text(gtm.get("summary", ""))
        
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(13, 71, 161)
        pdf.cell(0, 10, "COMPARATIVE CHANNEL STRATEGY (PARTNERS VS DIRECT):", 0, 1)
        pdf.body_text(gtm.get("channel_strategy", ""))
        
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(13, 71, 161)
        pdf.cell(0, 10, "INBOUND VS OUTBOUND DYNAMICS (STRATEGIC DELTA):", 0, 1)
        pdf.body_text(gtm.get("inbound_vs_outbound", ""))

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(13, 71, 161)
        pdf.cell(0, 10, "COMPARATIVE ECOSYSTEM LEVERAGE:", 0, 1)
        pdf.body_text(gtm.get("ecosystem_leverage", ""))
        print(f"[*] PDF: Rendered GTM Strategy Analysis")
    
    # 5 COHORT COMPARISON matrix
    pdf.add_page()
    pdf.section_title("COMPETITIVE COHORT ANALYSIS")
    pdf.body_text(data.get("cohort", "Cohort comparison benchmarking the baseline against the identified leader group."))
    print(f"[*] PDF: Rendered Cohort Analysis")

    # 6 PERFORMANCE INDEX
    pdf.add_page()
    pdf.section_title("MARKET PERFORMANCE INDEX")
    chart_performance(data.get("partners", []), baseline_name)
    if os.path.exists("performance.png"):
        pdf.image("performance.png", x=10, w=190)
        pdf.ln(5)
    else:
        pdf.body_text("[Chart data currently being synthesized for this cohort]")
    pdf.body_text(data.get("performance_index_context", "Assessment of market positioning based on cumulative scoring indices."))
    print(f"[*] PDF: Rendered Performance Index")

    # 7 FINANCIAL TRAJECTORY & OPERATIONAL SCALE
    pdf.add_page()
    pdf.section_title("FINANCIAL TRAJECTORY & OPERATIONAL SCALE")
    
    metrics_data = data.get("market_metrics", {})
    
    # 7.1 Revenue Trajectory Chart
    traj = metrics_data.get("revenue_trajectory")
    if traj:
        chart_revenue_trajectory(traj)
        if os.path.exists("revenue_trajectory.png"):
            pdf.image("revenue_trajectory.png", x=10, w=190)
            pdf.ln(5)
            
    # 7.2 Workforce Size Chart
    workforce = metrics_data.get("workforce_data")
    if workforce:
        chart_workforce_size(workforce)
        if os.path.exists("workforce_size.png"):
            pdf.image("workforce_size.png", x=10, w=190)
            pdf.ln(10)
            
    print(f"[*] PDF: Rendered Financial Trajectory & Scale")

    # 7.5 MARKET METRICS & SCALE (Visual Card-Based UI)
    if data.get("market_metrics"):
        pdf.add_page()
        pdf.section_title("MARKET METRICS & OPERATIONAL SCALE")
        metrics_data = data["market_metrics"]
        pdf.body_text(metrics_data.get("summary", ""))
        
        comp_list = metrics_data.get("comparison", [])
        if comp_list:
            # Helper for clean truncation
            def tr(text, length):
                text = str(text)
                return text[:length-3] + "..." if len(text) > length else text

            # ── TOP-LINE SUMMARY (Horizontal Cards) ──────────────────────────
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 8, "TOP-LINE SUMMARY", 0, 1)
            pdf.ln(2)
            
            card_w = 60
            card_h = 28
            spacing = 5
            start_x = pdf.get_x()
            curr_y = pdf.get_y()
            
            for i, item in enumerate(comp_list[:3]): 
                x = start_x + (i * (card_w + spacing))
                
                pdf.set_fill_color(252, 252, 252)
                pdf.rect(x, curr_y, card_w, card_h, 'F')
                pdf.set_draw_color(230, 230, 230)
                pdf.rect(x, curr_y, card_w, card_h, 'D')
                
                # Content
                revenue = str(item.get("annual_revenue", "N/A"))
                # Dynamic font size for revenue
                rev_font_size = 14 if len(revenue) < 10 else 10
                if len(revenue) > 20: rev_font_size = 8
                
                pdf.set_xy(x, curr_y + 3)
                pdf.set_font("Helvetica", "B", rev_font_size)
                c_name = item.get("company", "")
                if "Cognizant" in c_name: pdf.set_text_color(13, 71, 161)
                elif "Capgemini" in c_name or "Airtel" in c_name: pdf.set_text_color(0, 172, 193)
                else: pdf.set_text_color(255, 152, 0)
                
                pdf.multi_cell(card_w, 5, clean_text(revenue), 0, "C")
                
                # Company Name below revenue
                pdf.set_x(x)
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(120, 120, 120)
                pdf.cell(card_w, 4, tr(f"{c_name}", 25), 0, 1, "C")
                
                # Growth pill
                growth = item.get("growth_yoy", "0%")
                pdf.set_xy(x + 10, curr_y + 19)
                pdf.set_fill_color(240, 248, 255)
                pdf.set_font("Helvetica", "B", 7)
                pdf.set_text_color(13, 71, 161)
                pdf.cell(40, 5, tr(f"{growth} Growth", 25), 0, 0, "C", True)
            
            pdf.set_xy(start_x, curr_y + card_h + 10)
            
            # ── COMPANY PROFILES (Vertical Cards) ──────────────────────────
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 8, "COMPANY PROFILES", 0, 1)
            pdf.ln(2)
            
            prof_w = 60
            prof_h = 115 # Further increased for safety
            curr_y = pdf.get_y()
            
            for i, item in enumerate(comp_list[:3]):
                x = start_x + (i * (prof_w + spacing))
                
                pdf.set_fill_color(255, 255, 255)
                pdf.rect(x, curr_y, prof_w, prof_h, 'F')
                
                c_name = item.get("company", "")
                if "Cognizant" in c_name: pdf.set_draw_color(13, 71, 161)
                elif "Capgemini" in c_name or "Airtel" in c_name: pdf.set_draw_color(0, 172, 193)
                else: pdf.set_draw_color(255, 152, 0)
                pdf.set_line_width(1.0)
                pdf.line(x, curr_y, x + prof_w, curr_y)
                
                pdf.set_draw_color(220, 220, 220)
                pdf.set_line_width(0.2)
                pdf.rect(x, curr_y, prof_w, prof_h, 'D')
                
                # Header
                pdf.set_xy(x + 3, curr_y + 4)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(33, 37, 41)
                pdf.multi_cell(prof_w - 6, 4, tr(clean_text(item.get("company", "Company")), 40))
                
                pdf.set_x(x + 3)
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(120, 120, 120)
                pdf.multi_cell(prof_w - 6, 3.5, tr(clean_text(item.get("tagline", "Industry Player")), 60))
                
                pdf.ln(1)
                pdf.set_draw_color(245, 245, 245)
                pdf.line(x + 3, pdf.get_y(), x + prof_w - 3, pdf.get_y())
                pdf.ln(1)
                
                metrics = [
                    ("Revenue (est.)", item.get("annual_revenue", "N/A")),
                    ("Market share", item.get("market_share", "N/A")),
                    ("Typical deal size", item.get("avg_deal_size", "N/A")),
                    ("Global enterprise clients", item.get("client_count", "N/A")),
                    ("YoY growth", item.get("growth_yoy", "N/A"))
                ]
                
                for label, val in metrics:
                    pdf.set_x(x + 3)
                    pdf.set_font("Helvetica", "", 6.5)
                    pdf.set_text_color(150, 150, 150)
                    pdf.cell(prof_w - 6, 3.5, label, 0, 1)
                    
                    pdf.set_x(x + 3)
                    pdf.set_font("Helvetica", "B", 7.5)
                    pdf.set_text_color(33, 37, 41)
                    # Use multi_cell for values to prevent overflow
                    pdf.multi_cell(prof_w - 6, 3.5, tr(clean_text(val), 60))
                    pdf.ln(0.5)
                
                status = item.get("status_pill", "Stable")
                pdf.set_xy(x + 3, curr_y + prof_h - 9)
                pdf.set_fill_color(248, 249, 250)
                pdf.set_font("Helvetica", "B", 6.5)
                pdf.set_text_color(100, 100, 100)
                pdf.cell(30, 5, tr(status.upper(), 25), 0, 0, "C", True)

            pdf.set_xy(start_x, curr_y + prof_h + 10)
        
        print(f"[*] PDF: Rendered Market Cards (UI Fixed)")
        
        # 7.8 SOCIAL MEDIA & DIGITAL PRESENCE (PARENT COMPANY ONLY)
        pdf.add_page()
        pdf.section_title("SOCIAL MEDIA & DIGITAL PRESENCE")
        pdf.body_text("Brief assessment of the primary entity's visibility, engagement style, content strategy, and professional positioning across digital channels.")
        
        # ONLY SHOW THE PARENT COMPANY (First Partner)
        partners_list = data.get("partners", [])
        if partners_list:
            p = partners_list[0]
            raw_sm = p.get("social_media", {})
            if isinstance(raw_sm, dict):
                # --- DATA NORMALIZATION ---
                if "platforms" not in raw_sm and any(k in raw_sm for k in ["instagram", "linkedin", "twitter", "facebook"]):
                    sm_data = {
                        "overall_summary": "Legacy social data found. Strategic summary pending next scrape.",
                        "platforms": raw_sm,
                        "key_positioning": ["Legacy data record"],
                        "observations": ["Strategic assessment available upon re-scrape"]
                    }
                else:
                    sm_data = raw_sm
                
                platforms = sm_data.get("platforms", {})
                if isinstance(platforms, dict) and any(details.get("url") for details in platforms.values() if isinstance(details, dict) and details.get("url")):
                    pdf.ln(5)
                    pdf.set_font("Helvetica", "B", 12)
                    pdf.set_text_color(13, 71, 161)
                    pdf.cell(0, 10, f"{p['name'].upper()} (PRIMARY ENTITY)", 0, 1)
            
            # 1. Overall Digital Presence
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(0, 7, "Overall Digital Presence", 0, 1)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(33, 37, 41)
            pdf.multi_cell(0, 5, clean_text(sm_data.get("overall_summary", "Digital presence strategy focused on market reach and brand awareness.")))
            pdf.ln(5)
            
            # 2. Platform Presence Summary Table
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(0, 7, "Platform Presence Summary", 0, 1)
            
            try:
                with pdf.table(
                    borders_layout="MINIMAL",
                    cell_fill_color=(245, 247, 250),
                    cell_fill_mode="EVEN_ROWS",
                    line_height=6,
                    width=190,
                    col_widths=(30, 70, 90)
                ) as table:
                    header = table.row()
                    pdf.set_font("Helvetica", "B", 9)
                    header.cell("Platform")
                    header.cell("Presence & Communication Style")
                    header.cell("Primary Focus")
                    
                    pdf.set_font("Helvetica", "", 9)
                    for platform, info in platforms.items():
                        if not isinstance(info, dict) or not info.get("url"): continue
                        row = table.row()
                        row.cell(platform.capitalize())
                        row.cell(clean_text(info.get("brand_voice") or "Active Presence"))
                        row.cell(clean_text(info.get("bio") or "Market Engagement"))
            except Exception as table_err:
                print(f"[*] Social Table Rendering Error: {table_err}")
                pdf.body_text("[Social media platform summary data currently being reformatted for this partner]")
            
            pdf.ln(8)
            
            # 3. Key Digital Positioning
            pos = sm_data.get("key_positioning", [])
            if pos:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(50, 50, 50)
                pdf.cell(0, 7, "Key Digital Positioning", 0, 1)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(33, 37, 41)
                for item in pos[:4]:
                    pdf.set_x(15)
                    pdf.cell(5, 5, chr(149), 0, 0)
                    pdf.multi_cell(0, 5, clean_text(item))
                pdf.ln(5)
            
            # 4. Observations
            obs = sm_data.get("observations", [])
            if obs:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(50, 50, 50)
                pdf.cell(0, 7, "Observations", 0, 1)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(33, 37, 41)
                for item in obs[:4]:
                    pdf.set_x(15)
                    pdf.cell(5, 5, chr(149), 0, 0)
                    pdf.multi_cell(0, 5, clean_text(item))
                pdf.ln(5)
            
            pdf.ln(5)
        print(f"[*] PDF: Rendered Social Media Presence")

    # 8 INTERPRETATION
    pdf.add_page()
    pdf.section_title("STRATEGIC INTERPRETATION")
    pdf.body_text(data.get("interpretation", "Deep-dive analysis of current performance benchmarks and evidence-based technical moats."))

    # 8.5 STRATEGIC COMPARISON TABLE
    if data.get("comparison_matrix"):
        pdf.add_page()
        pdf.section_title("STRATEGIC COMPARISON TABLE")
        
        # Header Row
        header_style = FontFace(fill_color=(22, 33, 44), color=(255, 255, 255))
        pdf.set_font("Helvetica", "B", 9)
        
        # Reset fill color to avoid leakage from section_title
        pdf.set_fill_color(255, 255, 255)
        
        with pdf.table(
            borders_layout="ALL",
            cell_fill_color=(245, 247, 250),
            cell_fill_mode="EVEN_ROWS",
            line_height=pdf.font_size * 2,
            width=190,
            col_widths=(40, 50, 50, 50)
        ) as table:
            # Header Row
            h_row = table.row()
            h_row.cell(" COMPANY", style=header_style)
            h_row.cell(" STRENGTH", style=header_style)
            h_row.cell(" WEAKNESS", style=header_style)
            h_row.cell(" FOCUS", style=header_style)

            
            # Data Rows
            pdf.set_text_color(33, 37, 41)
            pdf.set_font("Helvetica", "", 8)
            matrix = data.get("comparison_matrix", [])
            if not matrix:
                # If matrix is missing, try to build it from the partner summaries
                for p in data.get("partners", []):
                    r = table.row()
                    r.cell(clean_text(p.get('name', 'Unknown')))
                    r.cell("Capability Audit In Progress")
                    r.cell("Market Gap Analysis Pending")
                    r.cell(clean_text(p.get('industries', ['General'])[0] if p.get('industries') else 'General'))
            else:
                for row_data in matrix: # Removed the [:10] limit
                    r = table.row()
                    r.cell(clean_text(row_data.get('Company', row_data.get('partner_name', 'Partner'))))
                    r.cell(clean_text(row_data.get('Strength', 'Capability Audit Pending')))
                    r.cell(clean_text(row_data.get('Weakness', 'Minimal Disclosure')))
                    r.cell(clean_text(row_data.get('Market_Focus', 'General Markets')))
        print(f"[*] PDF: Rendered Comparison Table")


    # 9 LEADERS DEEP-DIVE
    pdf.add_page()
    pdf.section_title("COMPETITOR DEEP-DIVE: STRENGTHS & GAPS")
    leaders = data.get("leaders", [])
    if not leaders:
        pdf.body_text("Comparative leader audit in progress. The current cohort is being benchmarked against global industry averages.")
    else:
        for leader in leaders:
            name = leader.get('name', 'Competitor').upper()
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(13, 71, 161)
            pdf.cell(0, 10, f">> {name}", 0, 1)
            
            # Label Above Value for safety
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(70, 70, 70)
            pdf.cell(0, 6, "PRIMARY STRENGTH:", 0, 1)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(33, 37, 41)
            pdf.multi_cell(0, 6, clean_text(leader.get('strength', 'Analysis pending source validation.')))
            pdf.ln(2)
            
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(70, 70, 70)
            pdf.cell(0, 6, "IDENTIFIED GAP / WEAKNESS:", 0, 1)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(33, 37, 41)
            pdf.multi_cell(0, 6, clean_text(leader.get('weakness', 'No significant gap identified in public data.')))
            pdf.ln(2)
            
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(100, 100, 100)
            evidence = leader.get('evidence', 'General market data audit')
            pdf.multi_cell(0, 6, f"SOURCE EVIDENCE: {evidence}")
            pdf.ln(8)
        print(f"[*] PDF: Rendered Competitor Deep-Dive")

    # 10 GAP ANALYSIS
    pdf.add_page()
    pdf.section_title("GAP ANALYSIS & VULNERABILITIES")
    gap_chart(data.get("gap_metrics", {})) if "gap_metrics" in data else None
    if os.path.exists("gap.png"):
        pdf.image("gap.png", x=20, w=170)
        pdf.ln(5)
    else:
        pdf.body_text("[Comparative gap analysis visualization pending additional market signals]")
    pdf.body_text(data.get("gap", "Assessment of baseline vulnerabilities based on identified market deltas."))
    print(f"[*] PDF: Rendered Gap Analysis")

    # 11 RECOMMENDATIONS
    pdf.add_page()
    pdf.section_title("ACTIONABLE RECOMMENDATIONS")
    
    recs = data.get("recommendations", [])
    if not recs:
        pdf.body_text("Strategic recommendations are being modeled based on current performance indices.")
    else:
        for i, r in enumerate(recs[:4]):
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(13, 71, 161)
            pdf.cell(0, 8, f"{i+1}. {r.get('title', 'Recommendation').upper()}", 0, 1)
            
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 6, f"Rationale: {clean_text(r.get('rationale', ''))}")
            
            pdf.ln(1)
            pdf.set_x(pdf.l_margin)  # Reset to left margin after multi_cell
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(70, 70, 70)
            pdf.cell(0, 6, "IMPLEMENTATION STEPS:", 0, 1)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(33, 37, 41)
            
            steps = r.get('implementation_steps', [])
            if isinstance(steps, list):
                for step in steps:
                    pdf.set_x(20)
                    pdf.multi_cell(180, 6, f"- {clean_text(str(step))}")
            else:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, clean_text(str(steps)))
            pdf.ln(4)
        print(f"[*] PDF: Rendered Recommendations")

    # 12 PATH TO DOMINANCE (Roadmap)
    pdf.add_page()
    pdf.section_title("12-MONTH STRATEGIC ROADMAP")
    path_data = data.get("path", "")
    if isinstance(path_data, list) and len(path_data) > 0:
        for item in path_data:
            if isinstance(item, dict):
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(13, 71, 161)
                pdf.cell(0, 8, clean_text(item.get("quarter", "Next Phase")), 0, 1)
                
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(33, 37, 41)
                pdf.cell(30, 6, "MILESTONE:", 0, 0)
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(0, 6, clean_text(item.get("milestone", "Objective alignment")), 0, 1)
                
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(30, 6, "CAPABILITIES:", 0, 0)
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(0, 6, clean_text(item.get("capabilities", "Resource allocation")), 0, 1)
                
                details = item.get("details", [])
                if isinstance(details, list):
                    pdf.set_font("Helvetica", "I", 9)
                    for d in details:
                        pdf.set_x(20) # Explicitly set X for indentation
                        pdf.multi_cell(180, 5, f"> {clean_text(str(d))}")
                pdf.ln(5)
        print(f"[*] PDF: Rendered Strategic Roadmap")
    else:
        pdf.body_text(str(path_data) if path_data else "12-month development roadmap modeling in progress.")

    # 13 PRODUCT BENCHMARKING
    if data.get("product_benchmarking"):
        pdf.add_page()
        pdf.section_title("PRODUCT & SOLUTION BENCHMARKING")
        
        # Restore bar chart
        chart_solutions(data["product_benchmarking"], baseline_name)
        if os.path.exists("solutions.png"):
            pdf.image("solutions.png", x=10, w=190)
            pdf.ln(5)
            pdf.body_text("Comparison of core products and solutions identified across the leader cohort, focusing on efficiency and technical complexity.")
            pdf.ln(5)
        
        # Using fpdf2 table for automatic wrapping
        header_style = FontFace(fill_color=(22, 33, 44), color=(255, 255, 255))
        pdf.set_font("Helvetica", "B", 9)
        prods = data["product_benchmarking"]
        
        with pdf.table(
            borders_layout="ALL",
            cell_fill_color=(240, 244, 248),
            cell_fill_mode="ROWS",
            line_height=pdf.font_size * 2,
            width=190,
            col_widths=(50, 70, 50, 20)
        ) as table:
            # Header Row
            h_row = table.row()
            h_row.cell(" PARTNER", style=header_style)
            h_row.cell(" SOLUTION", style=header_style)
            h_row.cell(" VERTICAL", style=header_style)
            h_row.cell(" EFF.", style=header_style)

            
            pdf.set_text_color(33, 37, 41)
            pdf.set_font("Helvetica", "", 8)
            if not prods:
                table.row().cell("  (Product landscape audit in progress - specific solution mapping pending)", colspan=4)
            else:
                last_partner = None
                for prod in prods:
                    r = table.row()
                    current_partner = prod.get('partner_name', 'N/A')
                    
                    # Suppress repeated partner names for a cleaner grouped look
                    if current_partner == last_partner:
                        r.cell("") 
                    else:
                        r.cell(clean_text(current_partner))
                        last_partner = current_partner
                        
                    r.cell(clean_text(prod.get('solution_identified', 'N/A')))
                    r.cell(clean_text(prod.get('target_vertical', 'N/A')))
                    r.cell(f"{prod.get('efficiency_score', '0')}%")
        print(f"[*] PDF: Rendered Product Benchmarking Section")
    else:
        print(f"[!] PDF Warning: Skipping Product Benchmarking (data missing)")

    
    pdf.ln(5)
    pdf.body_text("FINAL STRATEGIC INSIGHT:")
    pdf.set_font("Helvetica", "I", 11)
    final_insight = data.get("final_insight", data.get("Final_insight", "Strategy finalized."))
    pdf.multi_cell(0, 7, clean_text(final_insight), align='J')

    output_dir = "strategic reports"
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    
    # 1. Prepare global report path with timestamp
    from datetime import datetime
    base, ext = os.path.splitext(filename)
    if not ext: ext = ".pdf"
    
    # SANITIZE BASE NAME
    base = clean_filename(base)
    
    date_str = datetime.now().strftime("%d-%m-%Y_%H%M%S")
    final_filename = f"{base}_Analysis_{date_str}{ext}"
    global_path = os.path.join(output_dir, final_filename)
    
    # Save to global folder with retry
    try:
        pdf.output(global_path)
    except Exception as pdf_err:
        print(f"[!] Primary PDF write failed ({pdf_err}). Retrying with shortened name...", file=sys.stderr)
        final_filename = f"Strategic_Report_{date_str}{ext}"
        global_path = os.path.join(output_dir, final_filename)
        pdf.output(global_path)
    print(f"[*] PREMIUM STRATEGIC PDF report saved to Global Bank: {global_path}")
    
    # 2. Save a copy to the baseline company folder as requested
    try:
        safe_name = clean_filename(baseline_name)
        
        baseline_reports_dir = os.path.join("scraped_data", safe_name, "reports")
        if not os.path.exists(baseline_reports_dir):
            os.makedirs(baseline_reports_dir)
            
        company_report_path = os.path.join(baseline_reports_dir, final_filename)
        
        # Save another copy
        try:
            pdf.output(company_report_path)
            print(f"[+] Backup copy synced to Baseline folder: {company_report_path}")
        except Exception as p_err:
            print(f"[-] Backup write failed ({p_err}). Skipping copy.", file=sys.stderr)
    except Exception as e:
        print(f"[-] Failed to derive baseline folder for backup: {e}")

    # 3. Sync to Catalyst Cloud Storage
    catalyst_client.upload_report(global_path, company_name=baseline_name)

    return global_path

# =========================
# BRIDGE FUNCTIONS FOR MAIN.PY
# =========================

def save_partner_data(data: dict):
    """Saves partner data to TXT and JSON files inside a company-specific folder."""
    base_output_dir = "scraped_data"
    partner_name = data.get('name', 'Unknown')
    partner_id = data.get('partner_id', 'no_id')
    parent_company = data.get('parent_company') # Optional parent for competitor nesting
    
    # --- Refine Name for Folder ---
    safe_name = clean_filename(partner_name)
    
    # Create the company folder
    # --- INTELLIGENT PATH RESOLUTION ---
    # We prioritize the EXPLICIT parent_company request from the dashboard.
    # If no parent is provided (like during a Sync), we search for an existing folder.
    
    company_dir = None
    
    if parent_company:
        # User explicitly wants this as a competitor
        safe_parent = clean_filename(parent_company)
        company_dir = os.path.join(base_output_dir, safe_parent, "competitors", safe_name)
        data["relationship"] = {
            "type": "competitor",
            "parent_company": parent_company,
            "folder_path": f"{safe_parent}/competitors/{safe_name}"
        }
        print(f"[*] Mapping as competitor to: {parent_company}")
    else:
        # No parent requested, check if it already exists anywhere (for Sync/Updates)
        if partner_id and partner_id != "no_id":
            import glob
            pattern = os.path.join(base_output_dir, "**", f"*_{partner_id}.json")
            matches = glob.glob(pattern, recursive=True)
            if matches:
                company_dir = os.path.dirname(matches[0])
                print(f"[*] Found existing path for ID {partner_id}: {company_dir}")

    # Fallback to primary folder if no parent requested and no existing folder found
    if not company_dir:
        company_dir = os.path.join(base_output_dir, safe_name)
        data["relationship"] = {
            "type": "parent",
            "parent_company": None,
            "folder_path": safe_name
        }

    # --- DATA MERGING & SAFETY ---
    # Load existing data if it exists to preserve metadata and protect against scrape failures
    existing_data = {}
    json_path = None
    if os.path.exists(company_dir):
        existing_files = [f for f in os.listdir(company_dir) if f.endswith(f"_{partner_id}.json")]
        if existing_files:
            json_path = os.path.join(company_dir, existing_files[0])
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except: pass

    # 1. Safety: Do not overwrite a good name with "Unknown Partner" if scrape failed
    if partner_name == "Unknown Partner" and existing_data.get('name') and existing_data.get('name') != "Unknown Partner":
        partner_name = existing_data['name']
        data['name'] = partner_name
        print(f"[*] Safety: Restored name '{partner_name}' from existing data.")

    # 2. Safety: Do not overwrite a good overview with empty/null if scrape failed
    if (not data.get('overview') or "Content extraction failed" in data.get('overview', '')) and existing_data.get('overview'):
        data['overview'] = existing_data['overview']
        print(f"[*] Safety: Preserved existing overview for '{partner_name}'.")

    # 3. Persistence: Always keep the parent_company if we already have one (and no new one was provided)
    if not parent_company and existing_data.get('parent_company'):
        parent_company = existing_data['parent_company']
        data['parent_company'] = parent_company
        print(f"[*] Persistence: Preserved parent '{parent_company}' from existing data.")

    # 4. Comprehensive Section Merging (Blogs, Cases, Stories)
    # If the new scrape found 0 items but the old data had items, KEEP the old items.
    for key in ['blogs', 'case_studies', 'customer_stories']:
        new_items = data.get(key, [])
        old_items = existing_data.get(key, [])
        if not new_items and old_items:
            data[key] = old_items
            print(f"[*] Safety: Preserved {len(old_items)} {key} for '{partner_name}' (new scrape returned 0).")

    # --- ENVIRONMENT CHECK ---
    # Matches is_local_env() in dashboard.py:
    # Any PROJECT_STAGE other than 'production' = local mode = save files locally
    is_prod = os.getenv('PROJECT_STAGE', 'development').lower() == 'production'
    is_local = not is_prod

    print(f"[*] Storage mode: {'LOCAL' if is_local else 'PRODUCTION'} (PROJECT_STAGE={os.getenv('PROJECT_STAGE','development')})", file=sys.stderr)

    if is_local:
        if not os.path.exists(company_dir):
            os.makedirs(company_dir)
        
    # --- FILENAME PERSISTENCE ---
    filename_base = f"{safe_name}_{partner_id}"
    if not is_prod:
        if json_path:
            filename_base = os.path.basename(json_path).replace(".json", "")
        elif partner_id and partner_id != "no_id":
            # Only check local dir if it exists
            if os.path.exists(company_dir):
                existing_files = [f for f in os.listdir(company_dir) if f.endswith(f"_{partner_id}.json")]
                if existing_files:
                    filename_base = existing_files[0].replace(".json", "")

    # Generate JSON (Only if NOT in Production)
    json_path = os.path.join(company_dir, f"{filename_base}.json")
    if not is_prod:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Generate TXT (Detailed version - Only if NOT in Production)
    txt_path = os.path.join(company_dir, f"{filename_base}.txt")
    if not is_prod:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("="*60 + "\n")
            f.write(f"COMPANY: {partner_name}\n")
            f.write(f"ID     : {partner_id}\n")
            f.write(f"WEBSITE: {data.get('website', 'N/A')}\n")
            f.write(f"LINKEDIN: {data.get('linkedin', 'N/A')}\n")
            f.write(f"PARENT : {parent_company or 'None'}\n")
            f.write("="*60 + "\n\n")
            
            f.write(f"OVERVIEW:\n{'-'*60}\n{data.get('overview','')}\n\n")
            
            if data.get("analysis_summary"):
                f.write(f"AI ANALYSIS SUMMARY:\n{'-'*60}\n{data['analysis_summary']}\n\n")

            # Sections for blogs, cases, stories
            for label, key in [("BLOGS", "blogs"), ("CASE STUDIES", "case_studies"), ("CUSTOMER STORIES", "customer_stories")]:
                items = data.get(key, [])
                f.write(f"{label} ({len(items)} found):\n")
                f.write("="*60 + "\n")
                if not items:
                    f.write("  (none found)\n\n")
                else:
                    for i, item in enumerate(items, 1):
                        f.write(f"  [{i}] {item.get('title', 'Untitled')}\n")
                        f.write(f"      Link: {item.get('link', 'N/A')}\n")
                        content = item.get('content', '').strip()
                        if content and content != "Content extraction failed." and "skipping direct content extraction" not in content:
                            f.write(f"      Content:\n")
                            formatted = format_content_for_txt(content)
                            f.write(formatted + "\n")
                        else:
                            f.write("      Content: (not available)\n")
                        f.write("\n")
                    f.write("\n")
            
            # Social Media
            sm = data.get("social_media", {})
            if sm:
                f.write("SOCIAL MEDIA LINKS:\n")
                f.write("="*60 + "\n")
                for platform, details in sm.items():
                    if details:
                        url = details.get("url") if isinstance(details, dict) else details
                        f.write(f"  {platform.title()}: {url}\n")
                f.write("\n")

    # --- API Sync Integration ---
    webhook_url = os.getenv("API_WEBHOOK_URL")
    
    # --- Catalyst Cloud Sync with Error Handling ---
    # save_partner() handles create vs update routing based on parent_company:
    #   parent_company = None → always CREATE as new parent (even if same name exists)
    #   parent_company = "X"  → find X in storage and UPDATE it; create if not found
    #   This also handles creating combined records for competitors.
    try:
        result = catalyst_client.save_partner(data, parent_company=parent_company)
        if result:
            print(f"[+] Data synced to Catalyst Stratus: {data.get('name')}", file=sys.stderr)
        else:
            print(f"[!] Warning: Catalyst sync may have failed for '{data.get('name')}'. Local data saved.", file=sys.stderr)
    except Exception as catalyst_err:
        print(f"[!] Error syncing to Catalyst: {catalyst_err}. Local data is preserved.", file=sys.stderr)

    return txt_path


def send_to_webhook(data: dict, url: str):
    """Sends the scraped data to an external API webhook with authentication."""
    try:
        api_key = os.getenv("API_WEBHOOK_KEY", "")
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key
        }
        
        print(f"[*] Syncing data for '{data.get('name')}' to API: {url}...", file=sys.stderr)
        # We send the full JSON data object
        response = requests.post(url, json=data, headers=headers, timeout=15)
        
        if response.status_code in [200, 201]:
            print(f"[+] API Sync Successful: {response.status_code}", file=sys.stderr)
        else:
            print(f"[-] API Sync Failed: Status {response.status_code} - {response.text[:100]}", file=sys.stderr)
    except Exception as e:
        print(f"[-] API Sync Error: {e}", file=sys.stderr)

def save_report(content: str, filename: str):
    """Saves raw text report."""
    output_dir = "strategic reports"
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    
    # Sanitize filename: remove illegal characters
    filename = re.sub(r'[\\/*?:"<>|]', "_", filename).replace("https_", "").replace("http_", "")
    
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path

def repair_json(json_str: str) -> dict:
    """Attempts to fix common AI JSON syntax errors before parsing."""
    import re
    import json
    
    if not json_str:
        return {}

    # 1. Block Extraction: Find the outermost { }
    try:
        # Remove potential markdown wrappers
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
            
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}')
        if start_idx != -1 and end_idx != -1:
            json_str = json_str[start_idx:end_idx + 1]
    except Exception:
        pass

    # 2. Fix trailing commas before closing braces/brackets
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    
    # 2. Basic Cleanup: Strip extra whitespace and non-JSON prefixes/suffixes
    json_str = json_str.strip()
    
    # 3. Fix missing commas between properties (safely)
    # Only insert comma if we see "key": value \n "key"
    json_str = re.sub(r'("|\d|true|false|null)\s*\n\s*"', r'\1,\n"', json_str)
    
    # 4. Handle common unquoted string issues from AI
    # This is risky but helps with common "key": value cases where value is a URL or unquoted string
    # We only do it if the line looks like "key": http... or "key": something without quotes
    def quote_unquoted(match):
        key = match.group(1)
        val = match.group(2).strip()
        if val.startswith('"') or val.lower() in ['true', 'false', 'null'] or val.replace('.','',1).isdigit():
            return f'"{key}": {val}'
        return f'"{key}": "{val}"'
    
    # Only apply to keys we expect to be strings in the schema
    json_str = re.sub(r'"(company|website|summary|name|tagline|description|market_position)":\s*([^",}\]]+)(?=[,}\]])', quote_unquoted, json_str)
    
    # 4. Handle common "hallucinated" unquoted strings in keys or values (risky but helpful)
    # Example: "key": Pending -> "key": "Pending"
    
    # 5. Attempt to balance braces if truncated
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    if open_braces > close_braces:
        json_str += '}' * (open_braces - close_braces)
    
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    if open_brackets > close_brackets:
        json_str += ']' * (open_brackets - close_brackets)

    try:
        return json.loads(json_str)
    except Exception as first_err:
        print(f"[*] JSON Repair needed. Attempting partial extraction...")
        try:
            last_brace = json_str.rfind('}')
            if last_brace != -1:
                return json.loads(json_str[:last_brace+1])
        except: 
            pass
        
        print(f"[!] JSON Repair failed. Returning minimal structure. Error: {first_err}")
        return {
            "partners": [],
            "executive_summary": "Strategic analysis formatting error.",
            "cohort": "Market cohort analysis pending.",
            "interpretation": "Analysis formatting error.",
            "market_metrics": {"summary": "Data formatting error.", "comparison": []},
            "gtm_strategy_analysis": {"summary": "Analysis corrupted during generation."},
            "final_insight": "AI generation parsing error."
        }

def save_report_as_pdf(content: str, filename: str, partners_data: list = None):
    """Bridge to the new generate_report function with robust JSON cleaning and Self-Healing."""
    # Sanitize filename using unified logic
    base, ext = os.path.splitext(filename)
    clean_name = clean_filename(base)
    filename = f"{clean_name}.pdf"
    
    try:
        report_data = repair_json(content)
        
        # --- SELF-HEALING: Ensure all required keys exist for report generation ---
        required_keys = {
            "market_metrics": {"summary": "Market data analysis in progress.", "comparison": [], "revenue_trajectory": {}, "workforce_data": []},
            "product_benchmarking": [],
            "comparison_matrix": [],
            "gtm_strategy_analysis": {"summary": "GTM analysis in progress.", "channel_strategy": "N/A", "inbound_vs_outbound": "N/A", "ecosystem_leverage": "N/A"},
            "interpretation": "Strategic interpretation mapping in progress.",
            "final_insight": "Strategic directive finalizing.",
            "cohort": "Strategic cohort analysis pending.",
            "executive_summary": "Executive summary pending final audit."
        }
        for key, default in required_keys.items():
            if key not in report_data or not report_data[key]:
                print(f"[*] Self-Healing: Restoring missing key '{key}' with industry defaults.")
                report_data[key] = default
        
        # ALWAYS refresh/add partners data locally for stability
        if partners_data is not None:
            report_data["partners"] = []
            ai_benchmarking = {item.get("name"): item for item in report_data.get("performance_partners", [])}
            
            for i, p in enumerate(partners_data):
                p_name = p.get("name", "Unknown")
                ai_perf = ai_benchmarking.get(p_name)
                
                if ai_perf:
                    # ── QUALITY SCORING: Use AI's strategic assessment ──
                    scores = ai_perf.get("scores", {"technical_depth": 0, "customer_success": 0, "market_authority": 0})
                    confidence_level = ai_perf.get("confidence", "low")
                    fallback_used = ai_perf.get("is_fallback", False)
                else:
                    # Legacy fallback
                    blogs = len(p.get('blogs', []))
                    cases = len(p.get('case_studies', [])) + len(p.get('customer_stories', []))
                    total = blogs + cases
                    scores = {"technical_depth": min(100, blogs * 12 + 20) if blogs > 0 else 0,
                              "customer_success": min(100, cases * 15 + 20) if cases > 0 else 0,
                              "market_authority": min(100, total * 8 + 20) if total > 0 else 0}
                    confidence_level = "high" if total >= 6 else "medium"
                    fallback_used = False

                p_entry = {
                    "name": p_name,
                    "scores": scores,
                    "confidence_level": confidence_level,
                    "fallback_used": fallback_used
                }
                # Keep full content for the baseline (first partner) to show in report
                if i == 0:
                    p_entry.update({k: p.get(k) for k in ["overview", "blogs", "case_studies", "customer_stories", "social_media"]})
                else:
                    # Also include social media for competitors to show in the deep-dive
                    p_entry["social_media"] = p.get("social_media", {})
                
                report_data["partners"].append(p_entry)
        
        # FINAL SAFETY: Ensure 'partners' exists and is a list before passing to engine
        if "partners" not in report_data or not isinstance(report_data["partners"], list):
            report_data["partners"] = []
            
        return generate_report(report_data, filename=filename)
    except Exception as e:
        import traceback
        print(f"[-] AI JSON Parsing Error: {e}")
        traceback.print_exc()
        # Final emergency fallback - Still use professional PDF class
        pdf = ReportPDF(partner_name=filename.split('_')[0])
        pdf.add_page()
        pdf.section_title("EXECUTIVE STRATEGIC BRIEFING")
        pdf.body_text("The following intelligence was captured during a high-fidelity analysis cycle. " + 
                      "While the detailed visual indexing is finalized, the core strategic insights are summarized below.")
        
        # Clean text without technical JSON artifacts
        clean_content = content
        if clean_content.strip().startswith('{'):
            # Attempt a much cleaner visual representation
            try:
                import json
                temp_data = json.loads(clean_content)
                if isinstance(temp_data, dict) and "executive_summary" in temp_data:
                    clean_content = temp_data["executive_summary"]
            except:
                import re
                clean_content = re.sub(r'[{}"]', '', clean_content)
                clean_content = re.sub(r',\n', '\n', clean_content)
        
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, clean_text(clean_content))
        
        output_dir = "strategic reports"
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        path = os.path.join(output_dir, filename)
        pdf.output(path)
        return path
