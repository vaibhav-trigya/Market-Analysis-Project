import os
import json
import requests
import urllib3
from catalyst_client import catalyst_client
from dotenv import load_dotenv

# Disable SSL warnings for local testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

print("--- ADVANCED BUCKET DEBUG ---")
project_id = os.getenv("PROJECT_ID")
bucket = os.getenv("STRATUS_BUCKET")
print(f"Project: {project_id}")
print(f"Bucket: {bucket}")

token = catalyst_client._get_access_token()
print(f"Token acquired: {token[:10]}...")

# 1. Test Raw Listing
url = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket}/objects"
headers = {"Authorization": f"Zoho-oauthtoken {token}"}
params = {"prefix": "partners/"}

print(f"Calling: {url}")
resp = requests.get(url, headers=headers, params=params, verify=False)
print(f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    objects = data.get("data", {}).get("objects", [])
    print(f"[+] API returned {len(objects)} objects in 'partners/'.")
    for obj in objects:
        print(f"  - {obj.get('name')}")
else:
    print(f"[-] API Error: {resp.text}")

# 2. Test list_partners() function
print("\n--- Testing list_partners() function ---")
partners = catalyst_client.list_partners()
print(f"Result: Found {len(partners)} partners.")
