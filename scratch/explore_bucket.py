import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def explore_bucket():
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
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    
    # Try different listing endpoints
    endpoints = [
        f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket_name}/objects",
        f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket_name}/objects?prefix=",
    ]
    
    for url in endpoints:
        print(f"\n[*] Exploring: {url}")
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            objs = resp.json().get("data", {}).get("objects", [])
            print(f"[+] Found {len(objs)} objects:")
            for o in objs:
                print(f"  - {o.get('name') or o.get('object_name')}")
        else:
            print(f"[-] Status {resp.status_code}: {resp.text[:200]}")

if __name__ == "__main__":
    explore_bucket()
