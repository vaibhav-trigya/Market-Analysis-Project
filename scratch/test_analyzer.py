
import os
import sys
import json
from dotenv import load_dotenv

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer import PartnerAnalyzer

load_dotenv()

def test_analyzer():
    print("[*] Testing Gemini Analyzer...")
    analyzer = PartnerAnalyzer()
    
    if not analyzer.gemini_key:
        print("[!] GEMINI_API_KEY is missing in .env")
        return

    test_data = {
        "name": "Test Company",
        "overview": "A sample company for testing JSON generation."
    }
    
    print(f"[*] Model: {analyzer.gemini_model}")
    print("[*] Generating report JSON...")
    
    try:
        res = analyzer.generate_competitive_report(test_data, [])
        if res:
            print("[+] Success! Response received.")
            print(f"[*] Response Preview: {res[:200]}...")
        else:
            print("[-] Failure: Analyzer returned None.")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    test_analyzer()
