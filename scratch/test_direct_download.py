import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_direct_download():
    project_id = "39634000000012090"
    bucket_name = "test-scrapper"
    file_key = "reports/Wipro_Analysis_05-05-2026_101221.pdf"
    
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
    
    # Download Object API (Singular)
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket_name}/object/{file_key}"
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    
    print(f"[*] Attempting download from: {url}")
    resp = requests.get(url, headers=headers)
    print(f"[*] Status: {resp.status_code}")
    
    if resp.status_code == 200:
        print(f"[+] SUCCESS! Downloaded {len(resp.content)} bytes.")
    else:
        print(f"[-] FAILED: {resp.text}")

if __name__ == "__main__":
    test_direct_download()
