import os
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

print("--- TESTING PLURAL PROJECTS VARIATIONS ---")

# Variation A: Plural Projects + Plural Buckets
urlA = f"https://api.catalyst.zoho.in/baas/v1/projects/{project_id}/stratus/buckets/{bucket}/objects"
print(f"Testing (Projects + Buckets): {urlA}")
respA = requests.get(urlA, headers=headers, verify=False)
print(f"Status: {respA.status_code}")
if respA.status_code == 200: print("[SUCCESS!!] Use Variation A")

# Variation B: Just projects
urlB = f"https://api.catalyst.zoho.in/baas/v1/projects/{project_id}/stratus/bucket/{bucket}/objects"
print(f"Testing (Projects + Bucket): {urlB}")
respB = requests.get(urlB, headers=headers, verify=False)
print(f"Status: {respB.status_code}")

# Variation C: No baas prefix (Used in some newer versions)
urlC = f"https://api.catalyst.zoho.in/stratus/v1/projects/{project_id}/buckets/{bucket}/objects"
print(f"Testing (No BaaS prefix): {urlC}")
respC = requests.get(urlC, headers=headers, verify=False)
print(f"Status: {respC.status_code}")
