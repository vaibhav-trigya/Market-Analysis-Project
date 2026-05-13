import os
import requests
from dotenv import load_dotenv

load_dotenv()

def discover_projects():
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

    # List Projects
    url = "https://api.catalyst.zoho.in/baas/v1/project"
    resp = requests.get(url, headers=headers, verify=False)
    if resp.status_code == 200:
        projects = resp.json().get("data", [])
        print(f"\n[OK] FOUND {len(projects)} PROJECTS:")
        for p in projects:
            print(f" - {p.get('project_name')} (ID: {p.get('project_id')})")
    else:
        print(f"[!] Error: {resp.text}")

if __name__ == "__main__":
    discover_projects()
