import os
import json
import requests
from dotenv import load_dotenv

# Load env
load_dotenv()

def list_catalyst_tables():
    project_id = os.getenv("PROJECT_ID", "39634000000012090")
    client_id = os.getenv("ZOHO_CLIENT_ID")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET")
    refresh_token = os.getenv("ZOHO_DATASTORE_REFRESH_TOKEN") or os.getenv("ZOHO_REFRESH_TOKEN")

    print(f"[*] Fetching tables for Project: {project_id}...")

    # Get Access Token
    token_url = "https://accounts.zoho.in/oauth/v2/token"
    data = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token"
    }
    r = requests.post(token_url, data=data)
    access_token = r.json().get("access_token")
    
    if not access_token:
        print(f"[!] Failed to get token: {r.text}")
        return

    # List Tables API
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table"
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        tables = resp.json().get("data", [])
        print(f"\n[OK] Found {len(tables)} tables:")
        for t in tables:
            print(f" - Name: {t['table_name']} (ID: {t['table_id']})")
    else:
        print(f"[!] Error listing tables: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    list_catalyst_tables()
