import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def smoke_test():
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

    # Test 1: Empty Payload
    print("\n[SMOKE TEST 1] Empty Payload []")
    url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/{table_id}/row"
    resp = requests.post(url, headers=headers, json=[], verify=False)
    print(f"Status: {resp.status_code}, Response: {resp.text}")

    # Test 2: Fake Table ID
    print("\n[SMOKE TEST 2] Fake Table ID")
    url_fake = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/table/9999999999/row"
    resp_fake = requests.post(url_fake, headers=headers, json=[{"row_data": {"test": 1}}], verify=False)
    print(f"Status: {resp_fake.status_code}, Response: {resp_fake.text}")

if __name__ == "__main__":
    smoke_test()
