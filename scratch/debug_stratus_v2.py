import os
import json
import requests
import urllib3
from catalyst_client import catalyst_client
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

project_id = os.getenv("PROJECT_ID")
bucket = os.getenv("STRATUS_BUCKET")
token = catalyst_client._get_access_token()

headers = {"Authorization": f"Zoho-oauthtoken {token}"}

print("--- TESTING URL VARIATIONS ---")

# Variation 1: Plural 'buckets' (Common in Zoho)
url1 = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/buckets/{bucket}/objects"
print(f"Testing (Plural): {url1}")
resp1 = requests.get(url1, headers=headers, verify=False)
print(f"Status: {resp1.status_code}")
if resp1.status_code == 200: print("[SUCCESS] Found with /buckets/")

# Variation 2: Original (Singular)
url2 = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/bucket/{bucket}/objects"
print(f"Testing (Singular): {url2}")
resp2 = requests.get(url2, headers=headers, verify=False)
print(f"Status: {resp2.status_code}")

# Variation 3: List Buckets (To find correct path)
url3 = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/stratus/buckets"
print(f"Testing (List Buckets): {url3}")
resp3 = requests.get(url3, headers=headers, verify=False)
print(f"Status: {resp3.status_code}")
if resp3.status_code == 200:
    print(f"Available Buckets: {resp3.json()}")

# Variation 4: BaaS Objects
url4 = f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/buckets/{bucket}/objects"
print(f"Testing (Direct BaaS): {url4}")
resp4 = requests.get(url4, headers=headers, verify=False)
print(f"Status: {resp4.status_code}")
