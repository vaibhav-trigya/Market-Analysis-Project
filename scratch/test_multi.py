import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("ZOHO_CLIENT_ID")
client_secret = os.getenv("ZOHO_CLIENT_SECRET")
refresh_token = os.getenv("ZOHO_DATASTORE_REFRESH_TOKEN") or os.getenv("ZOHO_REFRESH_TOKEN")
project_id = os.getenv("PROJECT_ID", "39634000000012090")

def get_token():
    resp = requests.post(
        "https://accounts.zoho.in/oauth/v2/token",
        params={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        verify=False
    )
    return resp.json().get("access_token")

token = get_token()
headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
table_name = "Market_Analysis"
test_record = {
    "record_id": "99999"
}

payload = [{"row_data": test_record}]
url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_name}/row"
resp = requests.post(url, headers=headers, json=payload, verify=False)

print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")
