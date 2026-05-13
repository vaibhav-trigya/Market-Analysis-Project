import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def brute_force():
    project_id = "39634000000012090"
    table_id = "39634000000012262"
    
    # Get Token
    token_url = "https://accounts.zoho.in/oauth/v2/token"
    r = requests.post(token_url, data={
        "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
        "client_id": os.getenv("ZOHO_CLIENT_ID"),
        "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
        "grant_type": "refresh_token"
    }, verify=False)
    access_token = r.json().get("access_token")
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_id}/row"

    cols = [
        "record_id",
        "base_company_name",
        "competition_input_data",
        "s3_scrapped_url",
        "status_final_report_url",
        "created_at"
    ]

    for col in cols:
        print(f"\n[TESTING] Column: {col}")
        # Use a dummy value that fits the type
        val = 1234 if "id" in col else "test_val"
        if col == "created_at": val = "2026-05-08 12:00:00"
        
        payload = [{"row_data": {col: val}}]
        resp = requests.post(url, headers=headers, json=payload, verify=False)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    brute_force()
