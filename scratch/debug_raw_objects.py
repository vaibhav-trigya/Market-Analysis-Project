import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def debug_objects():
    project_id = "39634000000012090"
    bucket_name = "test-scrapper"
    
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
    
    # List Objects API
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket_name}/objects"
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    
    print(f"[*] Requesting: {url}")
    resp = requests.get(url, headers=headers)
    print(f"[*] Status: {resp.status_code}")
    
    try:
        data = resp.json()
        print("[*] RAW RESPONSE:")
        print(json.dumps(data, indent=2))
    except:
        print(f"[*] Text Response: {resp.text}")

if __name__ == "__main__":
    debug_objects()
