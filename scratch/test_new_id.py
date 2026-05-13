import os
import requests
import urllib3
from catalyst_client import catalyst_client
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# NEW ID from URL
new_project_id = "50041716687"
bucket = os.getenv("STRATUS_BUCKET")
token = catalyst_client._get_access_token()
headers = {"Authorization": f"Zoho-oauthtoken {token}"}

print(f"--- TESTING WITH PROJECT ID: {new_project_id} ---")

# Try the most likely India URL
url = f"https://api.catalyst.zoho.in/baas/v1/project/{new_project_id}/stratus/bucket/{bucket}/objects"
print(f"Testing: {url}")
resp = requests.get(url, headers=headers, verify=False)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    print(f"[SUCCESS!!] Objects found: {resp.json().get('data',{}).get('objects')}")
else:
    print(f"[-] Failed: {resp.text}")
