import sys
import os

# Ensure project modules are accessible
sys.path.append(os.getcwd())

from analyzer import PartnerAnalyzer
import json

def test_discovery(company_name, website):
    print(f"[*] Testing Social Discovery for: {company_name} ({website})")
    
    # Initialize analyzer (uses existing .env keys)
    analyzer = PartnerAnalyzer()
    
    # Run the new AI search discovery
    social_data = analyzer.find_social_links_with_ai(company_name, website)
    
    # Print the resulting JSON structure
    print("\n[+] DISCOVERED SOCIAL DATA (JSON):")
    print(json.dumps(social_data, indent=2))

if __name__ == "__main__":
    # Test with Trigya Innovations
    test_discovery("Trigya Innovations", "https://trigya.co.in/")
