import os
import json
import requests
from dotenv import load_dotenv

# Load env
load_dotenv()

def sniff_columns():
    project_id = "39634000000012090"
    table_id = "39634000000012262" # From previous check
    
    client_id = os.getenv("ZOHO_CLIENT_ID")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET")
    refresh_token = os.getenv("ZOHO_DATASTORE_REFRESH_TOKEN") or os.getenv("ZOHO_REFRESH_TOKEN")

    # Get Token
    token_url = "https://accounts.zoho.in/oauth/v2/token"
    r = requests.post(token_url, data={
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token"
    })
    access_token = r.json().get("access_token")
    
    # Get Columns API
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_id}/column"
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        cols = resp.json().get("data", [])
        print(f"\n[OK] REAL COLUMN NAMES:")
        for c in cols:
            print(f" - Column: {c}")
    else:
        print(f"[!] Error: {resp.text}")

if __name__ == "__main__":
    sniff_columns()
