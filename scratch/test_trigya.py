from agent import ZohoPartnerAgent
from analyzer import PartnerAnalyzer
import json

def test_trigya():
    agent = ZohoPartnerAgent(partner_name="ea6f6f5bfb463ebbb78dd9d18224a4bf", headless=True)
    with agent.analyzer.client as client: # Just to ensure we have a client if needed
        data = agent.run()
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
    test_trigya()
