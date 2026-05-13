import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def test_individual_columns():
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

    # Test columns INDIVIDUALLY
    test_rows = [
        {"record_id": 7777},
        {"base_company_name": "TestOnlyName"}
    ]

    for row in test_rows:
        print(f"\n[DEBUG] Testing SINGLE column: {list(row.keys())}")
        payload = [{"row_data": row}]
        resp = requests.post(url, headers=headers, json=payload, verify=False)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    test_individual_columns()
