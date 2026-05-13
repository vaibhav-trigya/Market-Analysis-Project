import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def test_formats():
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

    row = {
        "record_id": 12345,
        "base_company_name": "FormatTest",
        "competition_input_data": "{}",
        "s3_scrapped_url": "{}",
        "status_final_report_url": "[]",
        "created_at": "2026-05-08 12:00:00"
    }

    # Format 1: Table ID + [{"row_data": {...}}]
    print("\n[TEST 1] Table ID + List Wrapper")
    url1 = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_id}/row"
    resp1 = requests.post(url1, headers=headers, json=[{"row_data": row}], verify=False)
    print(f"Status: {resp1.status_code}, Response: {resp1.text}")

    # Format 2: Table Name + [{"row_data": {...}}]
    print("\n[TEST 2] Table Name + List Wrapper")
    url2 = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/Market_Analysis/row"
    resp2 = requests.post(url2, headers=headers, json=[{"row_data": row}], verify=False)
    print(f"Status: {resp2.status_code}, Response: {resp2.text}")

if __name__ == "__main__":
    test_formats()
