import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def inspect_names():
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
    
    # Get Columns API
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_id}/column"
    resp = requests.get(url, headers=headers, verify=False)
    cols = resp.json().get("data", [])
    
    print("\n[INSPECTING RAW COLUMN NAMES]")
    for c in cols:
        name = c.get("column_name", "")
        # Print with length and hex to find hidden spaces
        print(f" - Name: |{name}| (Len: {len(name)}, Hex: {name.encode().hex()})")

if __name__ == "__main__":
    inspect_names()
