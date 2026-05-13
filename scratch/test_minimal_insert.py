import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def test_minimal_insert():
    project_id = "39634000000012090"
    table_id = "39634000000012262"
    
    client_id = os.getenv("ZOHO_CLIENT_ID")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET")
    refresh_token = os.getenv("ZOHO_DATASTORE_REFRESH_TOKEN") or os.getenv("ZOHO_REFRESH_TOKEN")

    # 1. Get Token
    token_url = "https://accounts.zoho.in/oauth/v2/token"
    r = requests.post(token_url, data={
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token"
    }, verify=False)
    access_token = r.json().get("access_token")
    
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_id}/row"

    # Test columns one by one
    test_rows = [
        {"record_id": 8888, "base_company_name": "Test1"},
        {"record_id": 8889, "base_company_name": "Test2", "s3_scrapped_url": "{}"},
        {"record_id": 8890, "base_company_name": "Test3", "status_final_report_url": "[]"},
        {"record_id": 8891, "base_company_name": "Test4", "competition_input_data": "{}"}
    ]

    for row in test_rows:
        print(f"\n[DEBUG] Testing payload: {list(row.keys())}")
        payload = [{"row_data": row}]
        resp = requests.post(url, headers=headers, json=payload, verify=False)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    test_minimal_insert()
