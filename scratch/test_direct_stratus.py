import os
import requests
import urllib3
from catalyst_client import catalyst_client
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

token = catalyst_client._get_access_token()
headers = {"Authorization": f"Zoho-oauthtoken {token}"}

# Direct Stratus URL (S3 compatible listing)
url = "https://test-scrapper-development.zohostratus.in/?prefix=partners/"
print(f"Testing Direct Stratus Listing: {url}")

resp = requests.get(url, headers=headers, verify=False)
print(f"Status: {resp.status_code}")

if resp.status_code == 200:
    print("[SUCCESS!!] Stratus responded directly.")
    print(f"Content: {resp.text[:500]}") # It will likely be XML (S3 style)
else:
    print(f"[-] Failed: {resp.text[:200]}")
