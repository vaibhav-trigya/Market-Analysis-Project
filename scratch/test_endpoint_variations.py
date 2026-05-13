import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def test_variations():
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
    
    variations = [
        f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket_name}/objects",
        f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket_name}/object",
        f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket_name}/list",
        f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket_name}/objects?prefix=reports/",
    ]
    
    for url in variations:
        print(f"\n[*] Testing: {url}")
        resp = requests.get(url, headers=headers)
        print(f"[*] Status: {resp.status_code}")
        if resp.status_code == 200:
            print("[+] SUCCESS!")
            print(json.dumps(resp.json(), indent=2)[:500])
        else:
            try:
                print(f"[-] Fail: {resp.json().get('data', {}).get('error_code')}")
            except:
                print(f"[-] Fail: {resp.text[:100]}")

if __name__ == "__main__":
    test_variations()
