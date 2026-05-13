import os
import sys

# Ensure bundled dependencies in temp_libs are accessible
temp_libs_path = os.path.join(os.path.dirname(__file__), "temp_libs")
if os.path.exists(temp_libs_path) and temp_libs_path not in sys.path:
    sys.path.insert(0, temp_libs_path)

import subprocess
import glob
import json
import time
import re
from flask import Flask, render_template_string, send_from_directory, jsonify, request
from dotenv import load_dotenv

# Define the specific Python interpreter for this project (MUST be 3.13 for temp_libs compatibility)
TARGET_PYTHON = r"C:\Users\Administrator\miniconda3\python.exe"
if not os.path.exists(TARGET_PYTHON):
    # Fallback to common miniconda path if the above absolute path differs
    TARGET_PYTHON = sys.executable 

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
    # 5. Sanitize characters - allow only alpha-numeric and hyphens
    name = re.sub(r'[^a-z0-9-]', ' ', name).strip()
    # 6. Title case and join with underscores
    name = "_".join([w.capitalize() for w in name.split()])
    return name or "Unknown"

app = Flask(__name__)

@app.route('/health')
def health_check():
    """Health check for Catalyst AppSail."""
    return "Scrapper Agent is Running!", 200

# Paths - Using absolute paths to ensure data visibility
BASE_DIR = os.getcwd()
REPORT_DIR = os.path.join(BASE_DIR, "strategic reports")
COLLECTIONS_DIR = os.path.join(BASE_DIR, "partner_collections")
OUTPUT_DIR = os.path.join(BASE_DIR, "scraped_data")

from catalyst_client import catalyst_client

# Global task tracker
active_tasks = {
    "report": None,
    "scrape": None,
    "sync": None
}

# Persistent system state
system_state = {
    "status": "OPERATIONAL",
    "color": "#4ade80",
    "bg": "rgba(34, 197, 94, 0.1)"
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strategic Intelligence Hub | Competitive Analysis</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root {
            --bg-deep: #010409;
            --bg-card: rgba(13, 17, 23, 0.7);
            --accent-orange: #f97316;
            --accent-blue: #38bdf8;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --border: rgba(48, 54, 61, 0.5);
            --glass-blur: blur(20px);
            --navy-dark: #0d1117;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-deep);
            background-image: 
                radial-gradient(circle at 0% 0%, rgba(249, 115, 22, 0.1) 0%, transparent 40%),
                radial-gradient(circle at 100% 100%, rgba(56, 189, 248, 0.1) 0%, transparent 40%);
            color: var(--text-primary);
            display: flex;
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* Sidebar Glassmorphism */
        .sidebar {
            width: 300px;
            background: rgba(13, 17, 23, 0.8);
            backdrop-filter: var(--glass-blur);
            border-right: 1px solid var(--border);
            padding: 40px 24px;
            display: flex;
            flex-direction: column;
            position: fixed;
            height: 100vh;
            z-index: 1000;
        }

        .logo-container {
            margin-bottom: 48px;
            padding: 12px;
            background: white;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 30px rgba(0,0,0,0.5);
        }
        .logo-img { width: 100%; border-radius: 8px; }

        .main-workspace {
            margin-left: 300px;
            flex: 1;
            padding: 48px;
            max-width: 1400px;
            width: calc(100% - 300px);
            transition: all 0.3s ease;
        }

        /* Responsive Design */
        .mobile-header {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0;
            height: 70px;
            background: rgba(13, 17, 23, 0.9);
            backdrop-filter: var(--glass-blur);
            border-bottom: 1px solid var(--border);
            z-index: 1001;
            padding: 0 20px;
            align-items: center;
            justify-content: space-between;
        }

        .menu-toggle {
            background: none;
            border: none;
            color: var(--text-primary);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        @media (max-width: 1024px) {
            .sidebar {
                transform: translateX(-100%);
                transition: transform 0.3s ease;
                width: 280px;
                position: fixed !important;
                z-index: 2000 !important; /* Above everything */
            }
            .sidebar.active {
                transform: translateX(0);
                box-shadow: 0 0 50px rgba(0,0,0,0.8);
            }
            .main-workspace {
                margin-left: 0 !important;
                width: 100% !important;
                padding: 90px 16px 40px 16px !important;
                overflow-x: hidden;
            }
            .mobile-header {
                display: flex !important;
                z-index: 1500 !important;
            }
            .grid-dashboard {
                grid-template-columns: 1fr !important; /* Force stack */
                gap: 20px !important;
            }
            .search-area {
                flex-direction: column;
            }
            .search-area .btn {
                width: 100%;
            }
        }

        @media (max-width: 640px) {
            .glass-card {
                padding: 24px 16px !important;
                border-radius: 16px;
                margin-bottom: 24px;
            }
            .card-title {
                font-size: 18px !important;
                margin-bottom: 12px;
            }
            .card-subtitle {
                font-size: 12px !important;
                margin-bottom: 20px;
                line-height: 1.4;
            }
            .search-area {
                gap: 16px !important;
            }
            .input-glow {
                padding: 12px !important;
                font-size: 13px !important;
            }
            .btn {
                padding: 14px 20px !important;
                font-size: 14px !important;
            }
            .nav-label {
                font-size: 10px !important;
                margin-bottom: 12px !important;
            }
            .status-badge {
                padding: 6px 10px !important;
                font-size: 10px !important;
                border-radius: 20px !important;
                max-width: fit-content;
            }
            .status-badge span {
                display: none; /* Hide 'SYSTEM STATUS:' label on mobile */
            }
            .main-workspace header {
                flex-direction: column !important;
                align-items: flex-start !important;
                gap: 20px;
                margin-bottom: 32px !important;
            }
            .main-workspace h1 {
                font-size: 28px !important;
            }
        }

        /* Nav & Sections */
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.2); }
        }
        .animate-pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }

        .nav-section { margin-bottom: 32px; }
        .nav-label {
            font-family: 'Outfit', sans-serif;
            font-size: 11px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: var(--accent-blue);
            margin-bottom: 16px;
            display: block;
            text-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
            opacity: 0.9;
        }

        /* Buttons & Inputs */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            padding: 16px 24px;
            border-radius: 14px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid transparent;
            width: 100%;
            white-space: nowrap;
            letter-spacing: -0.2px;
        }

        .btn-primary {
            background: linear-gradient(135deg, #f97316 0%, #ea580c 100%);
            color: white;
            box-shadow: 0 8px 20px -4px rgba(234, 88, 12, 0.4);
            position: relative;
            overflow: hidden;
        }
        .btn-primary::after {
            content: '';
            position: absolute;
            top: -50%; left: -50%; width: 200%; height: 200%;
            background: linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent);
            transform: rotate(45deg);
            transition: 0.5s;
            opacity: 0;
        }
        .btn-primary:hover::after { left: 100%; opacity: 1; }
        .btn-primary:hover {
            transform: translateY(-3px) scale(1.02);
            box-shadow: 0 12px 25px -5px rgba(234, 88, 12, 0.6);
        }
        .btn-primary:active { transform: translateY(-1px); }

        .status-btn { 
            background: rgba(255,255,255,0.03); 
            border: 1px solid rgba(255,255,255,0.05);
            transition: all 0.3s ease;
            color: rgba(255,255,255,0.6);
        }
        .status-btn:hover { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.2); color: white; }
        .status-btn.active { background: rgba(249, 115, 22, 0.15); border-color: var(--accent-orange); color: white; }

        .btn-ghost {
            background: rgba(30, 41, 59, 0.3);
            backdrop-filter: blur(8px);
            border: 1px solid var(--border);
            color: var(--text-primary);
        }
        .btn-ghost:hover {
            background: rgba(30, 41, 59, 0.6);
            border-color: var(--accent-blue);
            color: var(--accent-blue);
        }

        /* Cards */
        .glass-card {
            background: linear-gradient(135deg, rgba(13, 17, 23, 0.8) 0%, rgba(13, 17, 23, 0.5) 100%);
            backdrop-filter: var(--glass-blur);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 32px;
            margin-bottom: 32px;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            position: relative;
            overflow: hidden;
        }
        .glass-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, var(--border), transparent);
        }
        .glass-card:hover { 
            border-color: var(--accent-orange);
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.6), 0 0 20px rgba(249, 115, 22, 0.1);
        }

        .card-header { margin-bottom: 28px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 16px; }
        .card-title {
            font-family: 'Outfit', sans-serif;
            font-size: 24px;
            font-weight: 800;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
            color: #fff;
            text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        }
        .card-subtitle { font-size: 14px; color: var(--text-secondary); line-height: 1.6; }

        /* Search Bar */
        .search-area {
            position: relative;
            display: flex;
            gap: 12px;
        }
        .input-glow {
            flex: 1;
            background: #0d1117;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px 18px;
            color: white;
            font-size: 14px;
            transition: all 0.3s;
            appearance: none;
        }
        .input-glow option {
            background-color: #0d1117;
            color: white;
            padding: 12px;
        }
        .input-glow:focus {
            outline: none;
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.1);
            background: rgba(2, 6, 23, 0.8);
        }
        .input-compact {
            padding: 10px 14px;
            font-size: 13px;
            border-radius: 10px;
        }

        /* Advanced Options */
        .advanced-trigger {
            margin-top: 16px;
            color: var(--text-secondary);
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            user-select: none;
        }
        .advanced-trigger:hover { color: var(--accent-blue); }

        .advanced-panel {
            display: none;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
        }

        /* History & Lists */
        .grid-dashboard {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 32px;
        }

        .list-container { 
            display: flex; 
            flex-direction: column; 
            gap: 12px; 
            max-height: 400px; 
            overflow-y: auto; 
            padding-right: 8px;
        }
        .list-container::-webkit-scrollbar { width: 5px; }
        .list-container::-webkit-scrollbar-track { background: rgba(255,255,255,0.02); }
        .list-container::-webkit-scrollbar-thumb { background: var(--accent-blue); border-radius: 10px; }

        .list-item {
            background: rgba(30, 41, 59, 0.3);
            border: 1px solid var(--border);
            padding: 16px 20px;
            border-radius: 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.2s;
        }
        .list-item:hover {
            background: rgba(30, 41, 59, 0.6);
            border-color: var(--accent-orange);
            transform: translateX(4px);
        }
        .item-main { 
            display: flex; 
            flex-direction: column; 
            gap: 4px; 
            overflow: hidden; /* Fix overflow */
            flex: 1;
        }
        .item-title { 
            font-size: 16px; 
            font-weight: 700; 
            color: #fff; 
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis; /* Add ... for long names */
        }
        .item-subtitle { font-size: 11px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1.5px; font-weight: 600; }

        /* Status Pills */
        .status-pill {
            padding: 4px 10px;
            border-radius: 99px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            background: rgba(56, 189, 248, 0.1);
            color: var(--accent-blue);
            border: 1px solid rgba(56, 189, 248, 0.2);
        }

        .toggle-view-btn {
            margin-top: 16px;
            text-align: center;
            font-size: 13px;
            font-weight: 700;
            color: var(--accent-blue);
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 1px;
            transition: all 0.2s;
            display: none;
        }
        .toggle-view-btn:hover { color: var(--accent-orange); text-shadow: 0 0 8px rgba(249, 115, 22, 0.4); }

        /* Animation */
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .animate-in { animation: fadeIn 0.5s ease-out forwards; }

        .progress-track {
            height: 6px;
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            overflow: hidden;
            margin-top: 16px;
            display: none;
        }
        .progress-fill {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, var(--accent-orange), #ea580c);
            transition: width 0.3s ease;
        }

        /* Custom Scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-deep); }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: #334155; }
        
        .animate-spin { animation: spin 1.5s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        
        @keyframes pulseGlow {
            0% { box-shadow: 0 0 0 0 rgba(234, 88, 12, 0.5); border-color: rgba(234, 88, 12, 0.5); }
            70% { box-shadow: 0 0 0 12px rgba(234, 88, 12, 0); border-color: rgba(234, 88, 12, 0.2); }
            100% { box-shadow: 0 0 0 0 rgba(234, 88, 12, 0); border-color: rgba(234, 88, 12, 0.5); }
        }
        .animate-pulse-glow { animation: pulseGlow 2s infinite; }
    </style>
</head>
<body>
    <div class="mobile-header">
        <div style="font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 18px; color: var(--accent-orange);">
            STRATEGIC HUB
        </div>
        <button class="menu-toggle" onclick="toggleSidebar()">
            <i data-lucide="menu"></i>
        </button>
    </div>

    <aside class="sidebar" id="sidebar">
        <div class="logo-container">
            <img src="https://scrapperagent.catalystappsail.in/logo" alt="Logo" class="logo-img" onerror="this.src='https://placehold.co/200x80/0d1117/f97316?text=STRATEGIC+HUB'">
        </div>
        
        <div class="nav-section" style="margin-bottom: 28px;">
            <span class="nav-label" style="font-size: 10px; margin-bottom: 12px;">Core Operations</span>
            <select id="sync-select" class="input-glow input-compact partner-select" style="width: 100%; margin-bottom: 12px; background: rgba(15, 23, 42, 0.4);">
                <option value="">(Global Ecosystem Sync)</option>
            </select>
            <button class="btn btn-ghost" onclick="syncCollections()" id="sync-btn" style="padding: 10px 14px; font-size: 13px; border-radius: 10px;">
                <i data-lucide="refresh-cw" size="16"></i> Sync Target Data
            </button>
        </div>

        <div class="nav-section">
            <span class="nav-label" style="font-size: 10px; margin-bottom: 12px;">Strategic Mapping</span>
            <div class="glass-card" style="padding: 18px; border-radius: 16px; background: rgba(15, 23, 42, 0.6); box-shadow: inset 0 0 15px rgba(0,0,0,0.2);">
                <label class="nav-label" style="font-size: 9px; opacity: 0.6; margin-bottom: 8px; letter-spacing: 1px;">Analytical Baseline</label>
                <select id="baseline-select-sidebar" class="input-glow input-compact partner-select" style="width: 100%; margin-bottom: 14px; background: rgba(2, 6, 23, 0.9);">
                    <option value="">(Default: First Partner)</option>
                </select>
                <button class="btn btn-primary animate-pulse-glow" onclick="runBulkReportSidebar()" id="bulk-btn-sidebar" style="padding: 12px 18px; font-size: 13px;">
                    <i data-lucide="map" size="18"></i> Generate Market Map
                </button>
                <div class="progress-track" id="report-progress-container-sidebar">
                    <div class="progress-fill" id="report-progress-bar-sidebar"></div>
                </div>
                <div id="status-text-sidebar" style="font-size: 11px; margin-top: 12px; color: var(--text-secondary);"></div>
            </div>
        </div>
    </aside>

        <div style="margin-top: auto; font-size: 11px; opacity: 0.5;">
            v1.2 Advanced Intelligence Agent
        </div>
    </aside>

    <main class="main-workspace">
        <header class="animate-in" style="margin-bottom: 48px; display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
                <h1 style="font-family: 'Outfit', sans-serif; font-size: 36px; letter-spacing: -0.5px;">Strategic Intelligence Hub</h1>
                <p style="color: var(--text-secondary); font-size: 16px; margin-top: 8px;">Autonomous competitive research & market mapping engine.</p>
            </div>
            <div id="header-status-badge" class="status-badge" style="background: {{ system_state.bg }}; color: {{ system_state.color }}; border-color: rgba(255,255,255,0.1); font-size: 12px; display: flex; align-items: center; gap: 8px; padding: 8px 16px; white-space: nowrap;">
                <span id="header-status-dot" class="animate-pulse" style="width: 8px; height: 8px; background: {{ system_state.color }}; border-radius: 50%;"></span>
                <span>SYSTEM STATUS:</span> <span id="header-status-text">{{ system_state.status }}</span>
            </div>
        </header>

        <section class="glass-card animate-in" style="animation-delay: 0.1s;">
            <div class="card-header">
                <h2 class="card-title"><i data-lucide="zap" style="color: var(--accent-orange)"></i> Intelligence Capture</h2>
                <p class="card-subtitle">Deploy the deep scraper to analyze any brand website or corporate profile.</p>
            </div>
            
            <div class="search-area">
                <input type="text" id="partnerQuery" class="input-glow" placeholder="Enter brand name or official domain URL...">
                <button id="scrapeBtn" class="btn btn-primary" onclick="scrapePartner()" style="width: auto; padding: 0 32px;">
                    Analyze Now
                </button>
            </div>

            <div class="advanced-trigger" onclick="toggleAdvanced()" style="margin-bottom: 12px;">
                <i data-lucide="chevron-right" id="adv-arrow" size="14"></i> Configure Extraction Parameters & Bypass Links
            </div>

            <div id="competitor-logic-container" style="padding: 16px; background: rgba(56, 189, 248, 0.05); border: 1px solid rgba(56, 189, 248, 0.1); border-radius: 12px; margin-bottom: 20px;">
                <label style="cursor: pointer; display: flex; align-items: center; gap: 12px;">
                    <input type="checkbox" id="is-competitor" onchange="toggleCompetitor()" style="width: 18px; height: 18px; accent-color: var(--accent-orange);"> 
                    <span style="font-size: 14px; font-weight: 600;">Map as Competitor to a Baseline Target</span>
                </label>
                <div id="parent-selector-container" style="display: none; margin-top: 16px;">
                    <span class="nav-label" style="font-size: 10px;">Select Parent Company</span>
                    <select id="parent-company" class="input-glow partner-select" style="padding: 10px; font-size: 13px; width: 100%; background: rgba(2, 6, 23, 0.9);">
                        <option value="">-- Select Main Target --</option>
                    </select>
                </div>
            </div>
            
            <div class="advanced-panel" id="advanced-options">
                
                <div>
                    <label class="nav-label" style="font-size: 10px;">Blog Discovery Bypass</label>
                    <input type="text" id="manual-blog" class="input-glow" style="padding: 12px;" placeholder="/insights">
                </div>
                <div>
                    <label class="nav-label" style="font-size: 10px;">Case Study Bypass</label>
                    <input type="text" id="manual-case" class="input-glow" style="padding: 12px;" placeholder="/success-stories">
                </div>
                <div>
                    <label class="nav-label" style="font-size: 10px;">Social: LinkedIn</label>
                    <input type="text" id="manual-linkedin" class="input-glow" style="padding: 12px;" placeholder="https://...">
                </div>
                <div>
                    <label class="nav-label" style="font-size: 10px;">Social: YouTube</label>
                    <input type="text" id="manual-youtube" class="input-glow" style="padding: 12px;" placeholder="https://...">
                </div>
            </div>

            <!-- Status Container - scrapeStatus wraps all feedback elements -->
            <div id="scrapeStatus" style="margin-top: 16px; display: none;">
                <div id="scrapeLoading" style="color: var(--accent-blue); display: flex; align-items: center; gap: 10px; font-size: 14px; margin-bottom: 12px;">
                    <i data-lucide="loader-2" class="animate-spin" size="18"></i>
                    <span id="scrape-text">Initializing extraction...</span>
                </div>

                <!-- Live Console -->
                <div id="live-console-container" style="background: #0d1117; border: 1px solid var(--border); border-radius: 12px; padding: 12px; margin-top: 12px; display: none;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="nav-label" style="font-size: 9px; margin-bottom: 0;">Live Intelligence Feed</span>
                        <div style="display: flex; gap: 6px;">
                            <span style="width: 8px; height: 8px; background: #f87171; border-radius: 50%;"></span>
                            <span style="width: 8px; height: 8px; background: #fbbf24; border-radius: 50%;"></span>
                            <span style="width: 8px; height: 8px; background: #4ade80; border-radius: 50%;"></span>
                        </div>
                    </div>
                    <div id="live-console" style="font-family: 'Courier New', monospace; font-size: 12px; color: #4ade80; max-height: 200px; overflow-y: auto; white-space: pre-wrap; line-height: 1.4; padding: 8px; background: rgba(0,0,0,0.3); border-radius: 6px;"></div>
                </div>

                <div id="scrapeSuccess" class="status-pill animate-in" style="background: rgba(34, 197, 94, 0.1); color: #4ade80; border-color: rgba(34, 197, 94, 0.2); margin-top: 12px; display: none;"></div>
                <div id="scrapeError" class="status-pill animate-in" style="background: rgba(239, 68, 68, 0.1); color: #f87171; border-color: rgba(239, 68, 68, 0.2); margin-top: 12px; display: none;"></div>
            </div>

        </section>

        <!-- Finalize & Record Section (Simplified) -->
        <section class="glass-card animate-in" style="animation-delay: 0.15s; border-color: var(--accent-blue);">
            <div class="card-header">
                <h2 class="card-title"><i data-lucide="save" style="color: var(--accent-blue)"></i> Finalize & Record</h2>
                <p class="card-subtitle">Select your baseline and record the entire operation. Strategic reports will be generated automatically.</p>
            </div>
            
            <div class="search-area" style="margin-bottom: 0;">
                <select id="baseline-select-final" class="input-glow partner-select" style="flex: 1;">
                    <option value="">-- Select Baseline Company to Record --</option>
                </select>
                <button id="record-btn" class="btn btn-op" onclick="recordOperation()" style="width: auto; padding: 0 40px; background: var(--accent-blue); color: #010409; border: none;">
                    <i data-lucide="save" size="18"></i> Record It
                </button>
                <button id="clear-records-btn" class="btn btn-op" onclick="clearOperations()" style="width: auto; padding: 0 24px; background: rgba(248,113,113,0.15); color: #f87171; border: 1px solid rgba(248,113,113,0.3);" title="Clear all operation history and logs">
                    <i data-lucide="trash-2" size="18"></i> Clear Records
                </button>
            </div>
            <div id="record-status-msg" style="margin-top: 12px; font-size: 12px; font-weight: 600; color: #4ade80; display: none;"></div>
        </section>

        <div class="grid-dashboard">
            <section class="glass-card animate-in" style="animation-delay: 0.2s;">
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: start;">
                    <div>
                        <h2 class="card-title"><i data-lucide="database" size="20"></i> Intelligence Bank</h2>
                        <p class="card-subtitle">Stored competitive data available for mapping.</p>
                    </div>
                    <button class="status-pill" onclick="toggleAllHistory()" id="toggleHistoryBtn" style="cursor: pointer; background: rgba(255,255,255,0.05);">0 Records</button>
                </div>
                <div id="history-list" class="list-container"></div>
                <div id="history-more-btn" class="toggle-view-btn" onclick="toggleAllHistory()">+ View Full Database</div>
            </section>

            <section class="glass-card animate-in" style="animation-delay: 0.3s;">
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: start;">
                    <div>
                        <h2 class="card-title"><i data-lucide="file-text" size="20"></i> Strategic Reports</h2>
                        <p class="card-subtitle">Generated market maps and gap analyses.</p>
                    </div>
                    <button class="status-pill" onclick="toggleAllReports()" id="toggleReportsBtn" style="cursor: pointer; background: rgba(255,255,255,0.05);">0 Reports</button>
                </div>
                <div id="report-list" class="list-container"></div>
                <div id="report-more-btn" class="toggle-view-btn" onclick="toggleAllReports()">+ View All Reports</div>
            </section>
        </div>
    </main>

    <script>
        let showAllHistory = false;
        let showAllReports = false;

        function toggleSidebar() {
            const sidebar = document.getElementById('sidebar');
            sidebar.classList.toggle('active');
            
            const icon = document.querySelector('.menu-toggle i');
            if (sidebar.classList.contains('active')) {
                icon.setAttribute('data-lucide', 'x');
            } else {
                icon.setAttribute('data-lucide', 'menu');
            }
            if (window.lucide) lucide.createIcons();
        }

        document.addEventListener('click', (e) => {
            const sidebar = document.getElementById('sidebar');
            const toggle = document.querySelector('.menu-toggle');
            if (window.innerWidth <= 1024 && 
                sidebar && sidebar.classList.contains('active') && 
                !sidebar.contains(e.target) && 
                !toggle.contains(e.target)) {
                toggleSidebar();
            }
        });

        window.onload = () => {
            if (window.lucide) lucide.createIcons();
            loadHistory();
            loadReports();
            loadParentCompanies();
        };

        function toggleAllHistory() { showAllHistory = !showAllHistory; loadHistory(); }
        function toggleAllReports() { showAllReports = !showAllReports; loadReports(); }

        function toggleAdvanced() {
            const opt = document.getElementById('advanced-options');
            const arrow = document.getElementById('adv-arrow');
            const isOpen = opt.style.display === 'grid';
            opt.style.display = isOpen ? 'none' : 'grid';
            arrow.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(90deg)';
            if (!isOpen) loadParentCompanies();
        }

        function toggleCompetitor() {
            const isComp = document.getElementById('is-competitor').checked;
            const container = document.getElementById('parent-selector-container');
            console.log("[UI] Mapping as competitor:", isComp);
            if (container) {
                container.style.display = isComp ? 'block' : 'none';
                if (isComp) loadParentCompanies();
            }
        }

        async function loadParentCompanies() {
            const sel = document.getElementById('parent-company');
            if (!sel) return;
            try {
                const response = await fetch('/list-partners');
                const data = await response.json();
                const partners = data.partners || [];
                
                // Save current selection
                const currentVal = sel.value;
                
                sel.innerHTML = '<option value="">-- Select Main Target --</option>';
                partners.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.name;
                    opt.textContent = p.display_name || p.name;
                    if (p.name === currentVal) opt.selected = true;
                    sel.appendChild(opt);
                });
            } catch (e) { console.error("Error loading parents:", e); }
        }

        async function loadHistory() {
            const list = document.getElementById('history-list');
            const btn = document.getElementById('toggleHistoryBtn');
            const moreBtn = document.getElementById('history-more-btn');
            try {
                const res = await fetch('/list-partners');
                const data = await res.json();
                const partners = data.partners || [];
                btn.innerText = partners.length + " Records";
                
                const display = showAllHistory ? partners : partners.slice(0, 4);
                list.innerHTML = display.map(p => `
                    <div class="list-item">
                        <div class="item-main">
                            <span class="item-title">${p.name}</span>
                            <span class="item-subtitle">${p.parent ? 'Competitor to ' + p.parent : 'Entity ID: ' + p.id}</span>
                        </div>
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <button onclick="deletePartner('${p.id}')" style="background: none; border: none; color: #f87171; cursor: pointer; padding: 4px; display: flex; align-items: center; justify-content: center; transition: all 0.2s;" title="Delete Record">
                                <i data-lucide="trash-2" size="14"></i>
                            </button>
                            <i data-lucide="${p.parent ? 'shield-alert' : 'check-circle'}" size="14" style="color: ${p.parent ? 'var(--accent-orange)' : 'var(--accent-blue)'}"></i>
                        </div>
                    </div>
                `).join('') || '<div style="opacity: 0.5; text-align: center; padding: 20px;">No records found.</div>';
                
                if (moreBtn) {
                    moreBtn.style.display = partners.length > 4 ? 'block' : 'none';
                    moreBtn.innerText = showAllHistory ? '- Show Less' : "+ View Full Database (" + partners.length + ")";
                }

                lucide.createIcons();
                console.log("[JS] Received partners from backend:", partners.length);

                const partnerSelectors = document.querySelectorAll('.partner-select');
                partnerSelectors.forEach(sel => {
                    const cur = sel.value;
                    const isSync = sel.id === 'sync-select';
                    sel.innerHTML = isSync ? '<option value="">(Global Ecosystem Sync)</option>' : '<option value="">(Default: Select Baseline)</option>';
                    
                    if (partners.length === 0) {
                        const opt = document.createElement('option');
                        opt.textContent = "-- No Partners Found --";
                        sel.appendChild(opt);
                    }

                    partners.forEach(p => {
                        const opt = document.createElement('option');
                        opt.value = p.name;
                        opt.textContent = p.display_name || p.name;
                        if (p.name === cur) opt.selected = true;
                        sel.appendChild(opt);
                    });
                });
            } catch (e) {
                console.error("Error in loadHistory:", e);
            }
        }

        async function loadReports() {
            const list = document.getElementById('report-list');
            const btn = document.getElementById('toggleReportsBtn');
            const moreBtn = document.getElementById('report-more-btn');
            try {
                const res = await fetch('/list-reports');
                const data = await res.json();
                const reports = data.reports || [];
                btn.innerText = reports.length + " Reports";
                
                const display = showAllReports ? reports : reports.slice(0, 4);
                list.innerHTML = display.map(f => `
                    <div class="list-item">
                        <a href="/download/${f.id || f}" class="item-title" style="text-decoration: none; color: inherit; display: flex; align-items: center; gap: 8px;">
                            <i data-lucide="download" size="14"></i> ${f.name || f}
                        </a>
                        <span class="status-pill" style="font-size: 9px;">PDF</span>
                    </div>
                `).join('') || '<div style="opacity: 0.5; text-align: center; padding: 20px;">No reports yet.</div>';
                
                if (moreBtn) {
                    moreBtn.style.display = reports.length > 4 ? 'block' : 'none';
                    moreBtn.innerText = showAllReports ? '- Show Less' : "+ View All Reports (" + reports.length + ")";
                }

                lucide.createIcons();
            } catch (e) {}
        }

        async function deletePartner(id) {
            if (!confirm("Are you sure you want to permanently delete this intelligence record from Stratus? This cannot be undone.")) return;
            
            try {
                const res = await fetch("/delete-partner/" + id);
                const data = await res.json();
                if (data.success) {
                    loadHistory();
                    loadParentCompanies();
                } else {
                    alert("Delete failed: " + data.error);
                }
            } catch (e) {
                alert("Error connecting to server for deletion.");
            }
        }

        async function scrapePartner() {
            const query = document.getElementById('partnerQuery').value;
            if (!query) return;

            const btn = document.getElementById('scrapeBtn');
            const statusBox = document.getElementById('scrapeStatus');
            const loading = document.getElementById('scrapeLoading');
            const statusText = document.getElementById('scrape-text');
            const success = document.getElementById('scrapeSuccess');
            const error = document.getElementById('scrapeError');
            
            btn.disabled = true;
            statusBox.style.display = 'block';
            loading.style.display = 'flex';
            statusText.innerText = 'Initializing extraction...';
            success.style.display = 'none';
            error.style.display = 'none';

            const initialRes = await fetch('/list-partners');
            const initialData = await initialRes.json();
            const initialCount = (initialData.partners || []).length;

            const manualLinks = {
                blog_url: document.getElementById('manual-blog').value,
                case_study_url: document.getElementById('manual-case').value,
                youtube_url: document.getElementById('manual-youtube').value,
                linkedin_url: document.getElementById('manual-linkedin').value
            };

            const parent = document.getElementById('is-competitor').checked ? document.getElementById('parent-company').value : '';

            try {
                let url = "/scrape-partner?query=" + encodeURIComponent(query) + "&manual=" + encodeURIComponent(JSON.stringify(manualLinks));
                if (parent) url += "&parent_company=" + encodeURIComponent(parent);
                
                const res = await fetch(url);
                const data = await res.json();
                
                if (data.success) {
                    let attempts = 0;
                    const maxAttempts = 1000;
                    const initialMaxMtime = Math.max(0, ...((initialData.partners || []).map(p => p.mtime || 0)));

                    if (window._scrapePoll) {
                        clearInterval(window._scrapePoll);
                        window._scrapePoll = null;
                    }

                    const consoleContainer = document.getElementById('live-console-container');
                    const consoleEl = document.getElementById('live-console');
                    if (consoleContainer) consoleContainer.style.display = 'block';

                    function stopPoll(isSuccess, message) {
                        if (window._scrapePoll) {
                            clearInterval(window._scrapePoll);
                            window._scrapePoll = null;
                        }
                        loading.style.display = 'none';
                        btn.disabled = false;
                        if (isSuccess) {
                            success.innerText = message || "SUCCESS: Intelligence Captured & Synthesized.";
                            success.style.display = 'inline-block';
                            loadHistory();
                            loadParentCompanies();
                        } else {
                            error.innerText = message || "Capture failed.";
                            error.style.display = 'inline-block';
                        }
                    }

                    window._scrapePoll = setInterval(async () => {
                        attempts++;
                        try {
                            const [currentRes, taskRes, logsRes] = await Promise.all([
                                fetch('/list-partners'),
                                fetch('/task-status/scrape'),
                                fetch('/get-logs/scrape')
                            ]);
                            const currentData = await currentRes.json();
                            const taskData    = await taskRes.json();
                            const logsText    = await logsRes.text();
                            const currentCount = (currentData.partners || []).length;

                            if (consoleEl && logsText) {
                                const wasAtBottom = consoleEl.scrollHeight - consoleEl.clientHeight <= consoleEl.scrollTop + 1;
                                consoleEl.textContent = logsText;
                                if (wasAtBottom) consoleEl.scrollTop = consoleEl.scrollHeight;
                            }

                            if (taskData.status === 'failed') {
                                stopPoll(false, "Capture Failed: " + (taskData.error || "Unknown error"));
                                return;
                            }

                            const isTaskCompleted = taskData.status === 'completed';
                            const isFileNew = currentCount > initialCount;

                            if (isTaskCompleted) {
                                stopPoll(true, "SUCCESS: Intelligence Captured & Synthesized.");
                            } else if (isFileNew) {
                                statusText.innerText = 'New target detected. Finalizing analysis...';
                            } else if (attempts >= maxAttempts) {
                                stopPoll(false, "Extraction timeout. Process may still be running in background.");
                            } else {
                                if (taskData.latest) statusText.innerText = taskData.latest;
                                else if (attempts > 6) statusText.innerText = 'Deep Content Extraction...';
                            }
                        } catch (pollErr) {
                            console.warn("Poll error:", pollErr);
                            if (attempts >= maxAttempts) {
                                stopPoll(false, "Connection lost during extraction.");
                            }
                        }
                    }, 3000);
                }
            } catch (e) {
                loading.style.display = 'none';
                error.innerText = "Extraction initiated. Check system logs.";
                error.style.display = 'inline-block';
                btn.disabled = false;
                setTimeout(loadHistory, 10000);
            }
        }

        async function syncCollections() {
            const baseline = document.getElementById('sync-select').value;
            const btn = document.getElementById('sync-btn');
            btn.style.opacity = '0.5';
            btn.innerHTML = '<i data-lucide="loader-2" class="animate-spin" size="18"></i> Synchronizing...';
            try {
                let url = '/sync';
                if (baseline) url += "?baseline=" + encodeURIComponent(baseline);
                const res = await fetch(url);
                const data = await res.json();
                console.log("Sync triggered for: " + (baseline || "Global"));
            } catch (e) { }
            finally {
                setTimeout(() => { 
                    btn.disabled = false; 
                    btn.style.opacity = '1';
                    btn.innerHTML = '<i data-lucide="refresh-cw" size="18"></i> Sync Target Data'; 
                    lucide.createIcons();
                }, 3000);
            }
        }

        async function runBulkReportSidebar() {
            const baseline = document.getElementById('baseline-select-sidebar').value;
            const btn = document.getElementById('bulk-btn-sidebar');
            const status = document.getElementById('status-text-sidebar');
            const progressBar = document.getElementById('report-progress-bar-sidebar');
            const progressContainer = document.getElementById('report-progress-container-sidebar');

            if (!baseline) {
                alert("Please select an Analytical Baseline first.");
                return;
            }

            btn.disabled = true;
            status.textContent = "Deploying Intelligence Mapper...";
            progressContainer.style.display = 'block';
            progressBar.style.width = '10%';

            try {
                const hResInit = await fetch('/list-reports');
                const hDataInit = await hResInit.json();
                const initialNewest = hDataInit.reports && hDataInit.reports.length > 0 ? hDataInit.reports[0] : null;

                const res = await fetch("/run-bulk?baseline=" + encodeURIComponent(baseline));
                const data = await res.json();

                if (data.success) {
                    let hasDownloaded = false;
                    let progress = 10;
                    let attempts = 0;

                    if (window._reportPoll) {
                        clearInterval(window._reportPoll);
                        window._reportPoll = null;
                    }

                    function stopReportPoll(isSuccess, message) {
                        if (window._reportPoll) {
                            clearInterval(window._reportPoll);
                            window._reportPoll = null;
                        }
                        btn.disabled = false;
                        status.style.color = isSuccess ? "#4ade80" : "#f87171";
                        status.textContent = message;
                        progressBar.style.width = isSuccess ? '100%' : '0%';
                        setTimeout(() => {
                            progressContainer.style.display = 'none';
                            status.textContent = "";
                            status.style.color = "";
                        }, isSuccess ? 8000 : 12000);
                    }

                    window._reportPoll = setInterval(async () => {
                        attempts++;
                        try {
                            if (progress < 95) {
                                progress += 1;
                                progressBar.style.width = progress + '%';
                            }

                            const [hRes, taskRes] = await Promise.all([
                                fetch('/list-reports'),
                                fetch('/task-status/report')
                            ]);
                            const hData    = await hRes.json();
                            const taskData = await taskRes.json();
                            const currentNewest = hData.reports && hData.reports.length > 0 ? hData.reports[0] : null;

                            if (taskData.status === 'failed') {
                                stopReportPoll(false, "Report Failed: " + (taskData.error || "Unknown error"));
                                return;
                            }

                            if (taskData.latest && progress < 90) {
                                status.textContent = taskData.latest;
                            }

                            const isTaskCompleted = taskData.status === 'completed';
                            const isFileNew = currentNewest && currentNewest !== initialNewest;

                            if ((isTaskCompleted || isFileNew) && !hasDownloaded) {
                                hasDownloaded = true;
                                stopReportPoll(true, "SUCCESS: Strategic Map Generated.");

                                if (currentNewest) {
                                    const link = document.createElement('a');
                                    link.href = "/download/" + (currentNewest.id || currentNewest);
                                    link.download = currentNewest.name || currentNewest;
                                    document.body.appendChild(link);
                                    link.click();
                                    document.body.removeChild(link);
                                }
                                loadReports();
                            } else if (attempts > 120) {
                                stopReportPoll(false, "FAILURE: Intelligence Mapping Timed Out.");
                            } else {
                                status.textContent = "Synthesizing Comparative Analysis...";
                            }
                        } catch (pollErr) {
                            console.warn("Report poll error:", pollErr);
                            if (attempts > 120) {
                                stopReportPoll(false, "Connection lost during report generation.");
                            }
                        }
                    }, 3000);
                } else {
                    throw new Error(data.error || "Launch failed");
                }
            } catch (e) {
                status.textContent = 'CRITICAL FAILURE: ' + e.message;
                status.style.color = "#f87171";
                btn.disabled = false;
                setTimeout(() => { progressContainer.style.display = 'none'; status.textContent = ""; status.style.color = ""; }, 10000);
            }
        }

        async function recordOperation() {
            const baseline = document.getElementById('baseline-select-final').value;
            const btn = document.getElementById('record-btn');
            
            if (!baseline) {
                alert("Please select a Baseline Company first.");
                return;
            }
            
            btn.disabled = true;
            btn.innerHTML = '<i class="animate-spin" data-lucide="loader-2" size="18"></i> Recording...';
            lucide.createIcons();
            
            try {
                const res = await fetch("/record-operation?baseline=" + encodeURIComponent(baseline));
                const data = await res.json();
                
                if (data.success) {
                    btn.style.background = '#4ade80';
                    btn.style.color = '#010409';
                    btn.innerHTML = '<i data-lucide="check-circle" size="18"></i> Recorded';
                    alert("Record #" + data.record_id + " saved successfully!");
                } else {
                    throw new Error(data.error || "Recording failed");
                }
            } catch (e) {
                console.error(e);
                alert("Failed to record operation: " + e.message);
                btn.disabled = false;
                btn.innerHTML = '<i data-lucide="save" size="18"></i> Record It';
            }
            lucide.createIcons();
        }

        async function clearOperations() {
            if (!confirm("Are you sure you want to clear ALL operation history?")) return;

            const btn = document.getElementById('clear-records-btn');
            btn.disabled = true;
            btn.innerHTML = '<i data-lucide="loader-2" size="18"></i> Clearing...';
            lucide.createIcons();

            try {
                const res = await fetch('/clear-operations');
                const data = await res.json();
                if (data.success) {
                    btn.style.background = 'rgba(74,222,128,0.15)';
                    btn.style.color = '#4ade80';
                    btn.style.borderColor = 'rgba(74,222,128,0.3)';
                    btn.innerHTML = '<i data-lucide="check-circle" size="18"></i> Cleared';
                    alert('Cleared successfully!');
                } else {
                    throw new Error(data.error || 'Clear failed');
                }
            } catch (e) {
                console.error(e);
                alert('Failed to clear records: ' + e.message);
            }
            btn.disabled = false;
            if (!btn.innerHTML.includes('Cleared')) {
                btn.innerHTML = '<i data-lucide="trash-2" size="18"></i> Clear Records';
            }
            lucide.createIcons();
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    mode = "LOCAL" if is_local_env() else "PRODUCTION"
    print(f"[*] Serving Dashboard in {mode} MODE from: {os.getcwd()}")
    return render_template_string(HTML_TEMPLATE, system_state=system_state)

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Intelligence Admin Portal | Database Control</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@700;800&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root {
            --bg: #020617;
            --card: #0f172a;
            --text: #f8fafc;
            --accent: #f97316;
            --border: rgba(255,255,255,0.08);
            --red: #ef4444;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            background: var(--bg); 
            color: var(--text); 
            font-family: 'Inter', sans-serif; 
            padding: 40px;
            min-height: 100vh;
        }
        .admin-container {
            max-width: 1200px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
        }
        h1 { font-family: 'Outfit', sans-serif; font-size: 32px; letter-spacing: -1px; }
        
        .grid {
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 30px;
        }

        .card { 
            background: var(--card); 
            padding: 30px; 
            border-radius: 24px; 
            border: 1px solid var(--border);
            box-shadow: 0 20px 50px rgba(0,0,0,0.5); 
        }
        
        h2 { font-size: 18px; margin-bottom: 20px; color: var(--accent); text-transform: uppercase; letter-spacing: 1px; }

        .btn-list { display: flex; flex-direction: column; gap: 12px; }
        .btn { 
            padding: 14px; 
            border-radius: 12px; 
            border: 1px solid transparent; 
            cursor: pointer; 
            font-weight: 700; 
            font-size: 14px; 
            transition: 0.3s; 
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        .btn-op { background: rgba(34, 197, 94, 0.1); color: #4ade80; border-color: rgba(34, 197, 94, 0.2); }
        .btn-main { background: rgba(245, 158, 11, 0.1); color: #fbbf24; border-color: rgba(245, 158, 11, 0.2); }
        .btn-lim { background: rgba(239, 68, 68, 0.1); color: #f87171; border-color: rgba(239, 68, 68, 0.2); }
        .btn:hover { transform: translateY(-2px); filter: brightness(1.2); }

        .status-preview { margin-top: 20px; padding: 12px; border-radius: 8px; font-size: 13px; background: rgba(255,255,255,0.03); text-align: center; }

        /* Database Table */
        .db-container {
            max-height: 70vh;
            overflow-y: auto;
            border-radius: 16px;
            border: 1px solid var(--border);
        }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { background: rgba(255,255,255,0.03); padding: 16px; font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 800; }
        td { padding: 16px; border-bottom: 1px solid var(--border); font-size: 14px; }
        tr:hover { background: rgba(255,255,255,0.02); }
        
        .badge {
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
        }
        .badge-parent { background: rgba(56, 189, 248, 0.1); color: #38bdf8; }
        .badge-comp { background: rgba(249, 115, 22, 0.1); color: #f97316; }

        .delete-btn {
            background: none;
            border: none;
            color: var(--red);
            cursor: pointer;
            opacity: 0.5;
            transition: 0.2s;
        }
        .delete-btn:hover { opacity: 1; transform: scale(1.1); }

        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
    </style>
</head>
<body>
    <div class="admin-container">
        <header>
            <h1>Admin Control Portal</h1>
            <a href="/" style="color: #64748b; text-decoration: none; font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px;">
                <i data-lucide="arrow-left" size="16"></i> Return to Dashboard
            </a>
        </header>

        <div class="grid">
            <div class="card">
                <h2>System Status</h2>
                <div class="btn-list">
                    <button class="btn btn-op" onclick="updateStatus('OPERATIONAL', '#4ade80', 'rgba(34, 197, 94, 0.1)')">
                        <i data-lucide="check-circle" size="18"></i> Set Operational
                    </button>
                    <button class="btn btn-main" onclick="updateStatus('MAINTENANCE', '#fbbf24', 'rgba(245, 158, 11, 0.1)')">
                        <i data-lucide="tool" size="18"></i> Set Maintenance
                    </button>
                    <button class="btn btn-lim" onclick="updateStatus('LIMITED', '#f87171', 'rgba(239, 68, 68, 0.1)')">
                        <i data-lucide="alert-triangle" size="18"></i> Set Limited Mode
                    </button>
                </div>
                <div id="status-text" class="status-preview">Current: {{ status }}</div>
            </div>

            <div class="card">
                <h2>Database Management</h2>
                <div class="db-container">
                    <table id="partner-table">
                        <thead>
                            <tr>
                                <th>Company Name</th>
                                <th>Type</th>
                                <th>Parent Target</th>
                                <th>ID</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="db-body">
                            <tr><td colspan="5" style="text-align:center; padding: 40px; color: #64748b;">Loading database...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- CID section removed as requested -->
    </div>

    </div>


    <script>
        lucide.createIcons();

        async function updateStatus(status, color, bg) {
            await fetch(`/update-status?status=${status}&color=${encodeURIComponent(color)}&bg=${encodeURIComponent(bg)}`);
            const st = document.getElementById('status-text');
            st.innerText = 'Current: ' + status;
            st.style.color = color;
        }

        async function loadAllPartners() {
            try {
                const res = await fetch('/list-all-partners');
                const data = await res.json();
                const partners = data.partners || [];
                const body = document.getElementById('db-body');
                
                body.innerHTML = partners.map(p => `
                    <tr>
                        <td style="font-weight: 600;">${p.name}</td>
                        <td>
                            <span class="badge ${p.parent ? 'badge-comp' : 'badge-parent'}">
                                ${p.parent ? 'Competitor' : 'Parent'}
                            </span>
                        </td>
                        <td style="color: #64748b; font-size: 13px;">${p.parent || '-'}</td>
                        <td style="font-family: monospace; font-size: 11px; opacity: 0.5;">${p.id}</td>
                        <td>
                            <button class="delete-btn" onclick="deleteEntry('${p.id}', '${p.name}')">
                                <i data-lucide="trash-2" size="18"></i>
                            </button>
                        </td>
                    </tr>
                `).join('');
                
                lucide.createIcons();
            } catch (e) {
                console.error("Failed to load database", e);
            }
        }

        async function deleteEntry(id, name) {

            if (!confirm(`CRITICAL: Permanently delete "${name}" from Stratus database and index?`)) return;
            
            try {
                const res = await fetch(`/delete-partner/${id}`);
                const data = await res.json();
                if (data.success) {
                    loadAllPartners();
                } else {
                    alert("Delete failed: " + data.error);
                }
            } catch (e) {
                alert("Connection error.");
            }
        }

        window.onload = () => {
            loadAllPartners();
        };
    </script>

</body>
</html>
"""

@app.route('/admin')
def admin():
    return render_template_string(ADMIN_TEMPLATE, status=system_state['status'])

@app.route('/update-status')
def update_status():
    global system_state
    system_state['status'] = request.args.get('status', 'OPERATIONAL')
    system_state['color'] = request.args.get('color', '#4ade80')
    system_state['bg'] = request.args.get('bg', 'rgba(34, 197, 94, 0.1)')
    return jsonify({"success": True})

@app.route('/get-logs/<task_type>')
def get_logs(task_type):
    log_path = f"{task_type}_last.log"
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                return content
        except Exception as e:
            return str(e)
    return ""

@app.route('/logo')
def get_logo():
    return send_from_directory(os.getcwd(), "logo.webp")

@app.route('/task-status/<task_type>')
def task_status(task_type):
    log_path = f"{task_type}_last.log"
    proc = active_tasks.get(task_type)
    
    # Get the latest message from the log
    latest_msg = "Running..."
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                if lines:
                    # Look for the last line that isn't a technical log
                    for line in reversed(lines):
                        # Markers to strip: [*], [+], [-], [!], [i], [?], [✓], [✗]
                        markers = ["[*]", "[+]", "[-]", "[!]", "[i]", "[?]", "[✓]", "[✗]"]
                        if any(kw in line for kw in markers):
                            temp_msg = line
                            for kw in markers:
                                temp_msg = temp_msg.replace(kw, "")
                            
                            # Clean up Step prefixes (e.g., "Step 3: Extracting..." -> "Extracting...")
                            temp_msg = re.sub(r'Step \d+:\s*', '', temp_msg)
                            latest_msg = temp_msg.strip()

                            # Shorten long URLs in status to keep UI clean
                            def shorten_url(m):
                                url = m.group(0)
                                if len(url) > 50:
                                    return url[:25] + "..." + url[-20:]
                                return url
                            latest_msg = re.sub(r'https?://[^\s]+', shorten_url, latest_msg)
                            break
                    else:
                        latest_msg = lines[-1].strip()

                if "SUCCESS: ANALYSIS COMPLETE" in content or "SUCCESS: SYNC COMPLETE" in content:
                    return jsonify({"status": "completed", "message": "Task finished successfully.", "latest": latest_msg})
                
                if "Traceback" in content or "NameError" in content or "Error" in content or "failed" in content.lower() or "Blocked" in content:
                    error_msg = "\n".join(lines[-10:]) if lines else "Unknown error in logs."
                    return jsonify({"status": "failed", "error": error_msg, "latest": latest_msg})
        except: pass

    if proc is not None:
        retcode = proc.poll()
        if retcode is None:
            return jsonify({"status": "running", "latest": latest_msg})
        if retcode == 0:
            return jsonify({"status": "completed", "latest": latest_msg})
        else:
            return jsonify({"status": "failed", "error": f"Process exited with code {retcode}", "latest": latest_msg})
    
    return jsonify({"status": "idle"})

@app.route('/scrape-partner')
def scrape_partner():
    query = request.args.get('query')
    manual = request.args.get('manual')
    parent = request.args.get('parent_company')
    try:
        # Use -u for unbuffered output to ensure real-time log updates
        # Use the specific target Python for background tasks
        cmd = [TARGET_PYTHON, "-u", "main.py", "--partner", query]
        if manual:
            cmd.extend(["--manual-links", manual])
        if parent:
            cmd.extend(["--parent-company", parent])
        
        # Log to file to capture errors
        log_f = open("scrape_last.log", "w", encoding="utf-8")
        active_tasks["scrape"] = subprocess.Popen(cmd, stdout=log_f, stderr=log_f, bufsize=1)
        return jsonify({"success": True, "message": "Scrape started in background"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/run-bulk')
def run_bulk():
    baseline = request.args.get('baseline')
    try:
        cmd = [TARGET_PYTHON, "main.py", "--bulk"]
        if baseline:
            cmd.extend(["--baseline", baseline])

        # Log to file to capture errors
        log_f = open("report_last.log", "w", encoding="utf-8")
        active_tasks["report"] = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
        return jsonify({"success": True, "message": "Report generation started in background."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/sync')
def sync():
    baseline = request.args.get('baseline')
    try:
        cmd = [TARGET_PYTHON, "main.py", "--sync"]
        if baseline:
            cmd.extend(["--baseline", baseline])
        
        active_tasks["sync"] = subprocess.Popen(cmd)
        return jsonify({"success": True, "message": f"Sync started for {baseline or 'Global'} in background."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/clear-operations')
def clear_operations():
    """
    Clears operation_history.json and operation_log.csv.
    In production mode, also removes them from Stratus.
    """
    try:
        history_file = os.path.join(BASE_DIR, "operation_history.json")
        csv_file     = os.path.join(BASE_DIR, "operation_log.csv")

        # Reset local files
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("")

        # If production, also clear from Stratus
        if not is_local_env() and catalyst_client.enabled:
            catalyst_client.upload_object("operation_history.json", "[]")
            catalyst_client.upload_object("operation_log.csv", "")
            print("[*] Cleared operation files from Stratus.")

        print("[*] Operation history and log cleared.")
        return jsonify({"success": True, "message": "Operation history and log have been cleared successfully."})
    except Exception as e:
        print(f"[!] Clear operations error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/record-operation')
def record_operation():
    """
    Captures the final state of a scraping/reporting workflow and saves it to
    the master operation_history.json log.

    LOCAL MODE  -> reads from local scraped_data/ and strategic reports/
    PRODUCTION  -> reads/writes history from Stratus bucket (not local files)
    Always inserts into Catalyst DataStore regardless of mode.
    """
    baseline = request.args.get('baseline')
    if not baseline:
        return jsonify({"success": False, "error": "Baseline company is required."})

    history_file = os.path.join(BASE_DIR, "operation_history.json")

    try:
        # 1. Load existing history — from Stratus in production, local in dev
        history = []
        if not is_local_env() and catalyst_client.enabled:
            # PRODUCTION: read history from Stratus bucket
            try:
                content = catalyst_client.download_object("operation_history.json")
                if content:
                    history = json.loads(content)
                    print(f"[*] Loaded {len(history)} records from Stratus history")
            except Exception as e:
                print(f"[*] No Stratus history yet: {e}")
                history = []
        else:
            # LOCAL: read from local file
            if os.path.exists(history_file):
                with open(history_file, "r", encoding="utf-8") as f:
                    try:
                        history = json.load(f)
                    except:
                        history = []

        # 2. Determine Next Record ID
        next_id = 1
        if history:
            next_id = max(h.get("record_id", 0) for h in history) + 1

        # 3. -- Gather Data - Local OR Cloud ----------------------------------
        all_partners = []

        if is_local_env():
            # -- LOCAL: read from local scraped_data/ folder ------------------
            print("[*] LOCAL MODE: Gathering partner data from local files...")
            if os.path.exists(OUTPUT_DIR):
                for root, dirs, files in os.walk(OUTPUT_DIR):
                    for f in files:
                        if f.endswith(".json"):
                            try:
                                with open(os.path.join(root, f), "r", encoding="utf-8") as file:
                                    d = json.load(file)
                                    all_partners.append({
                                        "data": d,
                                        "path": root,
                                        "file": f
                                    })
                            except:
                                pass
        else:
            # -- PRODUCTION: read from Stratus bucket ------------------------─
            print("[*] PRODUCTION MODE: Gathering partner data from Stratus bucket...")
            cloud_partners = catalyst_client.list_partners()
            for p in cloud_partners:
                partner_id       = p.get("partner_id", "unknown")
                partner_id_clean = str(partner_id).replace("ext_", "")
                file_name        = f"ext_{partner_id_clean}.json"
                all_partners.append({
                    "data": p,
                    "path": "stratus/partners",
                    "file": file_name
                })

        # 4. Find base company and its competitors
        base_data   = None
        competitors = []

        for p in all_partners:
            if (p['data'].get("name") == baseline and
                    not p['data'].get("parent_company")):
                base_data = p
                break

        if not base_data:
            return jsonify({
                "success": False,
                "error": f"Base company '{baseline}' data not found in file store."
            })

        for p in all_partners:
            if p['data'].get("parent_company") == baseline:
                competitors.append(p)

        print(f"[*] Found base: {baseline} | Competitors: {len(competitors)}")

        # 5. -- Build column data ----------------------------------------------

        # A. competition_input_data
        competitor_input = {
            "baseCompany": {
                "name":     base_data['data'].get("name"),
                "scrapeUrl": base_data['data'].get("website")
            },
            "competitors": [
                {
                    "name":     c['data'].get("name"),
                    "scrapeUrl": c['data'].get("website")
                } for c in competitors
            ]
        }

        # B. s3_scrapped_url - file paths in bucket or local
        report_urls     = []
        report_pattern  = baseline.replace(' ', '_')

        if is_local_env():
            # Local: scan strategic reports/ folder
            if os.path.exists(REPORT_DIR):
                for f in os.listdir(REPORT_DIR):
                    if f.endswith(".pdf") and report_pattern.lower() in f.lower():
                        report_urls.append(f"strategic reports/{f}")
        
        # ALWAYS check Cloud for reports (or at least try to sync them)
        try:
            cloud_reports = catalyst_client.list_reports()
            # Sort by mtime (newest first) to ensure we pick the latest report
            cloud_reports.sort(key=lambda x: x.get('mtime', 0), reverse=True)
            
            print(f"[*] Cloud Discovery: Found {len(cloud_reports)} total objects in reports/ folder.")
            
            # Clean the baseline name for searching
            search_term = clean_filename(baseline).lower()
            print(f"[*] Searching for report with cleaned term: '{search_term}'")
            
            for r in cloud_reports:
                fname = r.get("file_name", "")
                cname = r.get("company_name", "").lower()
                
                # Check if the cleaned search term matches the filename or index company name
                if search_term in clean_filename(fname).lower() or search_term == clean_filename(cname).lower():
                    cloud_path = f"reports/{fname}"
                    if cloud_path not in report_urls:
                        print(f"  [✓] Match Found (Index): {fname}")
                        report_urls.append(cloud_path)
            
            if not report_urls:
                print(f"  [✗] No matching reports found in bucket for {baseline}")
            else:
                print(f"[*] Final report count for {baseline}: {len(report_urls)}")
        except Exception as e:
            print(f"[*] Cloud Report discovery error: {e}")

        # 6. Build the full record row (Using RAW objects for clean storage)
        base_url = catalyst_client.get_base_url()
        file_prefix = "scraped_data/" if is_local_env() else "partners/"
        
        # A. Partner JSON URLs (Full clickable URLs)
        s3_links = {
            "base": f"{base_url}/{file_prefix}{base_data['file']}",
            "competitors": [f"{base_url}/{file_prefix}{c['file']}" for c in competitors]
        }
        
        # B. PDF Report URLs (Map internal 'strategic reports/' to Cloud 'reports/')
        final_report_links = []
        for r_path in report_urls:
            fname = r_path.split('/')[-1]
            final_report_links.append(f"{base_url}/reports/{fname}")

        new_record = {
            "record_id"              : next_id,
            "base_company_name"      : baseline,
            "competition_input_data" : competitor_input, # Store as dict
            "s3_scrapped_url"        : s3_links,         # Store as dict with full URLs
            "status_final_report_url": final_report_links, # Store as list with full URLs
            "created_at"             : time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # 7. Save history — Stratus in production, local in dev
        history.append(new_record)
        if not is_local_env() and catalyst_client.enabled:
            # PRODUCTION: save to Stratus only
            catalyst_client.upload_object(
                "operation_history.json",
                json.dumps(history, indent=2)
            )
            print(f"[*] Saved {len(history)} records to Stratus history")
        else:
            # LOCAL: save to local file
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)

        # 8. -- Insert into Catalyst DataStore (with safe key mapping & full Stratus URLs) --
        try:
            # Table ID for the Market_Analysis table
            table_id = "39634000000012262"

            # Helper: safely convert dict/list to JSON string
            def to_json_str(val):
                if isinstance(val, (dict, list)):
                    return json.dumps(val, ensure_ascii=False)
                if isinstance(val, str):
                    return val  # already a JSON string
                return str(val)

            # Build the payload for the Function Bridge
            datastore_payload = {
                "record_id"              : int(new_record["record_id"]),
                "base_company_name"      : str(new_record["base_company_name"]),
                "competition_input_data" : to_json_str(new_record["competition_input_data"]),
                "s3_scrapped_url"        : to_json_str(new_record["s3_scrapped_url"]),
                "status_final_report_url": to_json_str(new_record["status_final_report_url"]),
                "created_at"             : str(new_record["created_at"])
            }

            print(f"[*] Syncing Record #{new_record['record_id']} to DataStore Table {table_id}...")
            print(f"[DataStore] Keys being sent: {list(datastore_payload.keys())}")
            success = catalyst_client.insert_row_always(table_id, datastore_payload)
            data_store_status = "[OK] Synced to Cloud" if success else "[FAIL] Sync Failed - Check Diagnostic Above"
            print(f"[*] DataStore status: {data_store_status}")
            
        except Exception as e:
            print(f"[!] Catalyst Sync Mapping Error: {e}")

        # 9. CSV backup
        import csv, io
        csv_file   = os.path.join(BASE_DIR, "operation_log.csv")

        if not is_local_env() and catalyst_client.enabled:
            # PRODUCTION: read existing CSV from Stratus, append, save back
            existing_csv = ""
            try:
                # FIX: download_object returns bytes, we MUST decode to string for CSV joining
                content_bytes = catalyst_client.download_object("operation_log.csv")
                existing_csv = content_bytes.decode("utf-8") if content_bytes else ""
            except Exception:
                existing_csv = ""
            output    = io.StringIO()
            fieldnames = list(new_record.keys())
            writer    = csv.DictWriter(output, fieldnames=fieldnames)
            if not existing_csv.strip():
                writer.writeheader()
            else:
                output.write(existing_csv)
                if not existing_csv.endswith("\n"):
                    output.write("\n")
            writer.writerow(new_record)
            catalyst_client.upload_object("operation_log.csv", output.getvalue())
        else:
            # LOCAL: append to local CSV
            file_exists = os.path.isfile(csv_file)
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=list(new_record.keys()))
                if not file_exists:
                    writer.writeheader()
                writer.writerow(new_record)

        return jsonify({
            "success"  : True,
            "record_id": next_id,
            "message"  : f"Operation recorded successfully! [Table: {data_store_status}]",
            "csv_file" : "operation_log.csv"
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})

@app.route('/run-cloud-sync')
def run_cloud_sync():
    """Triggers a full recursive sync of all local data to Catalyst Cloud."""
    try:
        if not catalyst_client.enabled:
            return jsonify({"success": False, "error": "Catalyst not initialized. Check your environment variables."})
        
        # 1. Sync Scraped Data
        scraped_res = catalyst_client.sync_directory(OUTPUT_DIR, "scraped_data")
        
        # 2. Sync Reports
        reports_res = catalyst_client.sync_directory(REPORT_DIR, "reports")
        
        return jsonify({
            "success": True, 
            "message": "Cloud sync complete.",
            "scraped_data": scraped_res,
            "reports": reports_res
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/rebuild-index')
def rebuild_index():
    """
    Rebuilds partners/index.json by re-downloading each known partner file
    from Stratus and rebuilding the index. Works without bucket listing API.
    """
    try:
        if is_local_env():
            return jsonify({"success": False, "error": "Only works in production/cloud mode."})

        if not catalyst_client.enabled:
            return jsonify({"success": False, "error": "Catalyst not enabled - check tokens."})

        # 1. Try reading existing index first
        existing_index = []
        try:
            content = catalyst_client.download_object("partners/index.json")
            if content:
                existing_index = json.loads(content)
                print(f"[Rebuild] Found existing index with {len(existing_index)} entries")
        except:
            pass

        # 2. Re-validate each entry - re-download each file to confirm it exists
        valid_entries = []
        for entry in existing_index:
            file_key = entry.get("file_key")
            if not file_key:
                partner_id_clean = str(entry.get("partner_id","")).replace("ext_","")
                file_key = f"partners/ext_{partner_id_clean}.json"
            try:
                file_content = catalyst_client.download_object(file_key)
                if file_content:
                    data = json.loads(file_content)
                    valid_entries.append({
                        "partner_id":     data.get("partner_id", entry.get("partner_id")),
                        "name":           data.get("name", entry.get("name")),
                        "display_name":   data.get("display_name", data.get("name","")),
                        "parent_company": data.get("parent_company"),
                        "is_base":        not bool(data.get("parent_company")),
                        "file_key":       file_key
                    })
                else:
                    valid_entries.append(entry)
            except:
                valid_entries.append(entry)

        # 3. Upload rebuilt index
        catalyst_client.upload_object(
            "partners/index.json",
            json.dumps(valid_entries, indent=2),
            {"content_type": "application/json"}
        )

        parents     = [e for e in valid_entries if e.get("is_base")]
        competitors = [e for e in valid_entries if not e.get("is_base")]

        return jsonify({
            "success"      : True,
            "total"        : len(valid_entries),
            "parents"      : len(parents),
            "competitors"  : len(competitors),
            "parent_names" : [e.get("name") for e in parents],
            "message"      : "Index rebuilt successfully!"
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})


def is_local_env() -> bool:
    """
    Returns True when running on local machine.
    Detection priority:
      1. DISABLE_CATALYST=true          - always local
      2. X_CATALYST_APP_NAME exists     - AppSail cloud (NOT local)
      3. X_CATALYST_PROJECT_ID exists   - AppSail cloud (NOT local)
      4. PROJECT_STAGE == production    - cloud (NOT local)
      5. Everything else                - local
    """
    if os.getenv("DISABLE_CATALYST", "").lower() in ["true", "1", "yes"]:
        print("[ENV] DISABLE_CATALYST set - LOCAL mode")
        return True
    if os.getenv("X_CATALYST_APP_NAME") or os.getenv("X_CATALYST_PROJECT_ID"):
        print("[ENV] X_CATALYST vars detected - CLOUD/AppSail mode")
        return False
    stage = (os.getenv("PROJECT_STAGE") or "development").lower()
    if stage == "production":
        print("[ENV] PROJECT_STAGE=production - CLOUD mode")
        return False
    print("[ENV] No cloud indicators found - LOCAL mode")
    return True

def should_skip_local():
    """Returns True if running in Production/Deployed environment to force Cloud-only view."""
    return not is_local_env()

@app.route('/list-partners')
def list_partners():
    """
    Lists primary parent companies for the dropdown.

    LOCAL MODE  (PROJECT_STAGE != production):
      - Reads ONLY from local scraped_data/ folder
      - Never touches Catalyst Stratus
      - Shows all locally saved parent companies

    PRODUCTION MODE (PROJECT_STAGE = production):
      - Reads ONLY from Catalyst Stratus
      - Never reads local files
      - Shows all cloud-stored parent companies
    """
    partners_dict = {}

    if is_local_env():
        # - LOCAL MODE: read only from local scraped_data/ ------------------
        print("[*] LOCAL MODE: Reading partners from local scraped_data/...")
        if os.path.exists(OUTPUT_DIR):
            for root, dirs, files in os.walk(OUTPUT_DIR):
                for f in files:
                    if not f.endswith(".json"):
                        continue
                    filepath = os.path.join(root, f)
                    try:
                        with open(filepath, "r", encoding="utf-8") as file:
                            data = json.load(file)

                        name       = data.get("name", "Unknown")
                        partner_id = data.get("partner_id", "N/A")
                        parent     = data.get("parent_company")

                        # Check folder - competitors subfolder = not a parent
                        is_competitor_folder = "competitors" in root.lower()

                        if not parent and not is_competitor_folder:
                            key = f"{name}_{partner_id}"
                            if key not in partners_dict:
                                partners_dict[key] = {
                                    "name":         name,
                                    "display_name": name,
                                    "id":           partner_id,
                                    "is_base":      True,
                                    "parent":       None,
                                    "mtime":        os.path.getmtime(filepath),
                                    "source":       "local"
                                }
                    except Exception:
                        continue
        print(f"[*] LOCAL MODE: Found {len(partners_dict)} local parent companies.")

    else:
        # - PRODUCTION MODE: read only from Catalyst Stratus ----------------
        print("[*] PRODUCTION MODE: Fetching partners from Catalyst Stratus...")
        if catalyst_client.enabled:
            cloud_data = catalyst_client.list_partners()
            for data in cloud_data:
                try:
                    name       = data.get("name")
                    if not name or str(name).strip().lower() in ["unknown", "n/a", "none", "null"]:
                        continue # Skip items without a real name
                    
                    partner_id = data.get("partner_id", "N/A")
                    parent_val = data.get("parent_company")

                    # A company is a "Base/Parent" if it has no parent_company assigned
                    is_parent = True
                    if parent_val:
                        p_str = str(parent_val).strip().lower()
                        n_str = str(name).strip().lower()
                        if p_str and p_str not in ["", "none", "null", "n/a", "false"] and p_str != n_str:
                            is_parent = False
                    
                    if is_parent:
                        key = f"{name}_{partner_id}"
                        partners_dict[key] = {
                            "name":         name,
                            "display_name": name,
                            "id":           partner_id,
                            "is_base":      True,
                            "parent":       None,
                            "mtime":        time.time(),
                            "source":       "cloud"
                        }
                except Exception as e:
                    print(f"[-] Cloud parse error: {e}")
        print(f"[*] PRODUCTION MODE: Found {len(partners_dict)} cloud partners.")

    final_list = list(partners_dict.values())
    final_list.sort(key=lambda x: str(x.get('name', '')).lower())
    print(f"[*] Serving {len(final_list)} primary partners to dropdown.")
    return jsonify({"partners": final_list})

@app.route('/debug-partners')
def debug_partners():
    """Diagnostic route to see raw data from Catalyst."""
    if not catalyst_client.enabled:
        return jsonify({"error": "Catalyst not enabled"})
    data = catalyst_client.list_partners()
    
    # Calculate stats
    named_items = [d for d in data if d.get('name') and str(d.get('name')).lower() not in ["unknown", "n/a", "none"]]
    parent_items = [d for d in named_items if not d.get('parent_company')]
    
    return jsonify({
        "total_count": len(data),
        "valid_named_count": len(named_items),
        "parent_count": len(parent_items),
        "is_local": is_local_env(),
        "summary_of_names": [d.get('name') for d in named_items],
        "raw_data": data
    })

@app.route('/list-all-partners')
def list_all_partners():
    """
    Lists EVERY company (Parents + Competitors).
    LOCAL MODE: reads local scraped_data/ only.
    PRODUCTION: reads Catalyst Stratus only.
    """
    partners_dict = {}

    if is_local_env():
        # LOCAL: read all JSON from scraped_data/
        if os.path.exists(OUTPUT_DIR):
            for root, dirs, files in os.walk(OUTPUT_DIR):
                for f in files:
                    if not f.endswith(".json"):
                        continue
                    try:
                        with open(os.path.join(root, f), "r", encoding="utf-8") as file:
                            data = json.load(file)
                        name       = data.get("name", "Unknown")
                        partner_id = data.get("partner_id", "N/A")
                        parent     = data.get("parent_company")
                        key = f"{name}_{partner_id}"
                        if key not in partners_dict:
                            partners_dict[key] = {
                                "name": name, "id": partner_id,
                                "parent": parent, "source": "Local"
                            }
                    except: continue
    else:
        # PRODUCTION: read from Stratus only
        if catalyst_client.enabled:
            cloud_data = catalyst_client.list_partners()
            for data in cloud_data:
                name       = data.get("name", "Unknown")
                partner_id = data.get("partner_id", "N/A")
                parent     = data.get("parent_company")
                key = f"{name}_{partner_id}"
                partners_dict[key] = {
                    "name": name, "id": partner_id,
                    "parent": parent, "source": "Cloud"
                }

    final_list = list(partners_dict.values())
    final_list.sort(key=lambda x: str(x.get('name', '')).lower())
    response = jsonify({"partners": final_list})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/delete-partner/<partner_id>')
def delete_partner_route(partner_id):
    """
    Deletes a partner record from Stratus AND Local filesystem.
    This prevents the record from reappearing due to local-cloud merging.
    """
    results = {"cloud": False, "local": False}
    try:
        # 1. DELETE FROM CLOUD (Stratus + index.json)
        if catalyst_client.enabled:
            results["cloud"] = catalyst_client.delete_partner(partner_id)
            
        # 2. DELETE FROM LOCAL (scraped_data)
        if os.path.exists(OUTPUT_DIR):
            import glob
            import shutil
            # Search for JSON and TXT files containing the partner_id
            pattern = os.path.join(OUTPUT_DIR, "**", f"*_{partner_id}.*")
            matches = glob.glob(pattern, recursive=True)
            
            for path in matches:
                try:
                    # If it's a file, remove it
                    if os.path.isfile(path):
                        os.remove(path)
                        results["local"] = True
                        print(f"[*] Deleted local file: {path}")
                    
                    # Optional: Clean up empty directories
                    parent_dir = os.path.dirname(path)
                    if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                        os.rmdir(parent_dir)
                        print(f"[*] Removed empty local directory: {parent_dir}")
                except Exception as local_e:
                    print(f"[-] Local delete error for {path}: {local_e}")

        if results["cloud"] or results["local"]:
            return jsonify({
                "success": True, 
                "message": f"Partner {partner_id} removed.",
                "details": results
            })
        else:
            return jsonify({"success": False, "error": "No records found to delete (Cloud or Local)."})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/list-reports')
def list_reports():
    """
    Lists generated PDF reports.
    LOCAL MODE: reads only from local strategic reports/ folder.
    PRODUCTION: reads only from Catalyst Stratus reports/.
    """
    try:
        report_details = []

        if is_local_env():
            # LOCAL: read from local report folder only
            if os.path.exists(REPORT_DIR):
                local_files = [f for f in os.listdir(REPORT_DIR) if f.endswith('.pdf')]
                for f in local_files:
                    path = os.path.join(REPORT_DIR, f)
                    mtime = os.path.getmtime(path)
                    report_details.append({"name": f, "mtime": mtime})
                print(f"[*] LOCAL MODE: Found {len(report_details)} local reports.")
        else:
            # PRODUCTION: read from Stratus only
            if catalyst_client.enabled:
                cloud_files = catalyst_client.list_reports()
                for cf in cloud_files:
                    report_details.append({
                        "name": cf.get('file_name'),
                        "mtime": cf.get('mtime', 0)
                    })
                print(f"[*] PRODUCTION MODE: Found {len(report_details)} cloud reports.")

        # Sort by mtime (descending)
        report_details.sort(key=lambda x: x['mtime'], reverse=True)
        final_list = [r['name'] for r in report_details]

        return jsonify({"reports": final_list})
    except Exception as e:
        return jsonify({"reports": [], "error": str(e)})

@app.route('/pull-cloud-data')
def pull_cloud_data():
    """Triggers a full sync FROM Catalyst Cloud to local storage (Data Recovery)."""
    try:
        if not catalyst_client.enabled:
            return jsonify({"success": False, "error": "Catalyst not initialized."})
        
        # 1. Pull Scraped Data
        scraped_res = catalyst_client.sync_from_cloud("scraped_data/", OUTPUT_DIR)
        
        # 2. Pull Reports
        reports_res = catalyst_client.sync_from_cloud("reports/", REPORT_DIR)
        
        return jsonify({
            "success": True, 
            "message": "Data recovery from cloud complete.",
            "scraped_data": scraped_res,
            "reports": reports_res
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/download/<filename>')
def download_file(filename):
    local_path = os.path.join(REPORT_DIR, filename)
    if os.path.exists(local_path):
        return send_from_directory(REPORT_DIR, filename, as_attachment=True, download_name=filename)
    
    # Fallback to Catalyst Stratus
    if catalyst_client.enabled:
        # Check cloud files
        content = catalyst_client.download_object(f"reports/{filename}")
        if content:
            from flask import Response
            return Response(content, mimetype='application/pdf', 
                          headers={"Content-Disposition": f"attachment;filename={filename}"})
        
        # FINAL FAIL-SAFE: If server-side fetch fails, redirect directly to the Stratus URL
        # which the user confirmed is working in their browser.
        from flask import redirect
        direct_url = catalyst_client._object_url(f"reports/{filename}")
        print(f"[*] Fallback: Redirecting to direct Stratus URL: {direct_url}")
        return redirect(direct_url)
    
    return "File not found or storage not accessible", 404

# --- SECURE TRIGGER API ---
@app.route('/api/trigger-scrape', methods=['POST'])
def api_trigger_scrape():
    """External API to trigger a scrape session remotely."""
    try:
        # 1. Verify API Key
        provided_key = request.headers.get("X-API-Key")
        master_key = os.getenv("SCRAPER_API_KEY")
        
        if not master_key or provided_key != master_key:
            return jsonify({"error": "Unauthorized. Invalid or missing X-API-Key."}), 401
            
        # 2. Extract parameters
        data = request.json or {}
        partner_name = data.get("partner_name")
        parent_company = data.get("parent_company")
        
        if not partner_name:
            return jsonify({"error": "Missing 'partner_name' in request body."}), 400
            
        # 3. Prevent duplicate tasks
        if active_tasks["scrape"] and active_tasks["scrape"].poll() is None:
            return jsonify({"error": "A scraping task is already in progress. Please wait."}), 429
            
        # 4. Trigger Scrape via Subprocess
        print(f"[*] API Triggered Scrape: {partner_name} (Parent: {parent_company})")
        cmd = [sys.executable, "main.py", "--partner", partner_name, "--headless"]
        if parent_company:
            cmd.extend(["--parent_company", parent_company])
            
        log_f = open("scrape_last.log", "w", encoding="utf-8")
        process = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
        active_tasks["scrape"] = process
        
        return jsonify({
            "message": "Scrape task initialized successfully.",
            "partner": partner_name,
            "parent_company": parent_company,
            "status": "RUNNING",
            "status_check_url": "/api/status/scrape"
        }), 202
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/trigger-report', methods=['POST'])
def api_trigger_report():
    """External API to trigger report generation remotely."""
    try:
        # 1. Verify API Key
        provided_key = request.headers.get("X-API-Key")
        master_key = os.getenv("REPORT_API_KEY")
        
        if not master_key or provided_key != master_key:
            return jsonify({"error": "Unauthorized. Invalid or missing X-API-Key."}), 401
            
        # 2. Extract parameters
        data = request.json or {}
        baseline_company = data.get("baseline_company")
        
        if not baseline_company:
            return jsonify({"error": "Missing 'baseline_company' in request body."}), 400
            
        # 3. Prevent duplicate tasks
        if active_tasks["report"] and active_tasks["report"].poll() is None:
            return jsonify({"error": "A report generation task is already in progress. Please wait."}), 429
            
        # 4. Trigger Report via Subprocess
        # This uses the existing --bulk --baseline logic which automatically handles peer relations
        print(f"[*] API Triggered Report: {baseline_company}")
        cmd = [sys.executable, "main.py", "--bulk", "--baseline", baseline_company]
        
        # Log to file
        log_f = open("report_last.log", "w", encoding="utf-8")
        process = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
        active_tasks["report"] = process
        
        return jsonify({
            "message": "Report generation initialized successfully.",
            "baseline": baseline_company,
            "status": "RUNNING",
            "status_check_url": "/api/status/report",
            "info": "Peer relationships will be automatically adjusted based on selection."
        }), 202
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/trigger-sync', methods=['POST'])
def api_trigger_sync():
    """External API to trigger data synchronization remotely."""
    try:
        # 1. Verify API Key
        provided_key = request.headers.get("X-API-Key")
        master_key = os.getenv("SYNC_API_KEY")
        
        if not master_key or provided_key != master_key:
            return jsonify({"error": "Unauthorized. Invalid or missing X-API-Key."}), 401
            
        # 2. Extract parameters
        data = request.json or {}
        baseline = data.get("baseline")
        
        # 3. Prevent duplicate tasks
        if active_tasks["sync"] and active_tasks["sync"].poll() is None:
            return jsonify({"error": "A synchronization task is already in progress. Please wait."}), 429
            
        # 4. Trigger Sync via Subprocess
        print(f"[*] API Triggered Sync: {baseline or 'Global Ecosystem'}")
        cmd = [sys.executable, "main.py", "--sync"]
        if baseline:
            cmd.extend(["--baseline", baseline])
            
        log_f = open("sync_last.log", "w", encoding="utf-8")
        process = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
        active_tasks["sync"] = process
        
        return jsonify({
            "message": "Sync task initialized successfully.",
            "baseline": baseline or "Global Ecosystem",
            "status": "RUNNING",
            "status_check_url": "/api/status/sync"
        }), 202
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/status/<task_type>', methods=['GET'])
def api_task_status(task_type):
    """External API to check task status with authentication."""
    try:
        # 1. Verify API Key (using any of the relevant keys)
        provided_key = request.headers.get("X-API-Key")
        keys = [os.getenv("SCRAPER_API_KEY"), os.getenv("REPORT_API_KEY"), os.getenv("SYNC_API_KEY")]
        
        if not provided_key or provided_key not in keys:
            return jsonify({"error": "Unauthorized. Invalid or missing X-API-Key."}), 401
            
        # 2. Reuse the existing status logic
        return task_status(task_type)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/test-datastore')
def api_test_datastore():
    """
    Diagnostic API to verify Catalyst DataStore connectivity and refresh token logic.
    """
    try:
        test_id = int(time.time())
        test_record = {
            "record_id"              : test_id,
            "base_company_name"      : "REFRESH_TOKEN_TEST",
            "competition_input_data" : json.dumps({"test": True, "type": "auth_check"}),
            "s3_scrapped_url"        : json.dumps({"status": "verified"}),
            "status_final_report_url": json.dumps(["test_report.pdf"]),
            "created_at"             : time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        print(f"[*] Triggering DataStore Auth Test (ID: {test_id})...")
        
        project_id = "39634000000012090"
        table_name = "Market_Analysis"
        headers = catalyst_client._auth_headers("application/json", is_datastore=True)
        
        if not headers:
            return jsonify({"success": False, "error": "Auth failed: Could not fetch access token. Check ZOHO_DATASTORE_REFRESH_TOKEN in .env"}), 500
            
        url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_name}/row"
        import requests
        resp = requests.post(url, headers=headers, json=[{"row_data": test_record}], verify=False, timeout=30)
        
        if resp.status_code == 401:
            headers = catalyst_client._auth_headers("application/json", is_datastore=True, force_refresh=True)
            resp = requests.post(url, headers=headers, json=[{"row_data": test_record}], verify=False, timeout=30)

        if resp.status_code in (200, 201):
            return jsonify({"success": True, "message": "Connectivity verified!", "catalyst_response": resp.json()})
        else:
            return jsonify({
                "success": False, 
                "status_code": resp.status_code,
                "catalyst_error": resp.json() if resp.headers.get('Content-Type') == 'application/json' else resp.text,
                "details": "Check your table name and column types in Catalyst console."
            }), 500
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    import sys
    # Handle optional command line arguments for host/port (for Docker)
    h = '0.0.0.0'
    p = int(os.environ.get("PORT", 8080))
    
    for arg in sys.argv:
        if arg.startswith('--host='): h = arg.split('=')[1]
        if arg.startswith('--port='): p = int(arg.split('=')[1])

    print(f"[*] Starting Dashboard on {h}:{p}")
    app.run(host=h, port=p, debug=False)