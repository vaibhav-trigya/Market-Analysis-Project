import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def test_column_ids():
    project_id = "39634000000012090"
    table_id = "39634000000012262"
    
    # Get Token
    token_url = "https://accounts.zoho.in/oauth/v2/token"
    r = requests.post(token_url, data={
        "refresh_token": os.getenv("ZOHO_DATASTORE_REFRESH_TOKEN"),
        "client_id": os.getenv("ZOHO_CLIENT_ID"),
        "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
        "grant_type": "refresh_token"
    }, verify=False)
    access_token = r.json().get("access_token")
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_id}/row"

    # Test cases: Uppercase, Names, IDs
    cases = [
        {"CASE": "Title Case", "row": {"Record_id": 1, "Base_company_name": "CaseTest"}},
        {"CASE": "All Caps", "row": {"RECORD_ID": 2, "BASE_COMPANY_NAME": "CapsTest"}},
        {"CASE": "Column IDs", "row": {"39634000000019238": 3, "39634000000019244": "IDTest"}}
    ]

    for c in cases:
        print(f"\n[TESTING] {c['CASE']}")
        payload = [{"row_data": c['row']}]
        resp = requests.post(url, headers=headers, json=payload, verify=False)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    test_column_ids()
