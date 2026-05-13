import os
import ssl
import requests
import urllib3

# --- SSL FIX ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

old_request = requests.Session.request
def patched_request(self, *args, **kwargs):
    kwargs['verify'] = False
    kwargs.setdefault('timeout', 30)
    return old_request(self, *args, **kwargs)
requests.Session.request = patched_request

# --- GET ACCESS TOKEN ---
print("Fetching access token...")
token_resp = requests.post("https://accounts.zoho.in/oauth/v2/token", params={
    "grant_type": "refresh_token",
    "client_id": "1000.S4UP3226EYHCGYSNF9J2OHC3ATLXMI",
    "client_secret": "22861b6b17c8a89a9542404bd107f747cf70e69b65",
    "refresh_token": "1000.5229f79b10124d84eef12a293ace021b.2aa65d89def398a2f50b9b367e87b544"
}, verify=False, timeout=30)

token_data = token_resp.json()
access_token = token_data.get("access_token")
if not access_token:
    print("ERROR: Could not get access token!", token_data)
    exit(1)
print("Got access token!")

# --- PREPARE FILE ---
file_path = "file.txt"
if not os.path.exists(file_path):
    with open(file_path, "w") as f:
        f.write("Hello from Catalyst Test")

bucket_name = "test-scrapper"
object_key = "file.txt"

# --- UPLOAD TO STRATUS (India DC) ---
upload_url = f"https://{bucket_name}-development.zohostratus.in/{object_key}"
print(f"Uploading to: {upload_url}")

with open(file_path, "rb") as f:
    resp = requests.put(
        upload_url,
        headers={
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/octet-stream",
        },
        data=f,
        verify=False,
        timeout=30
    )

print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

if resp.status_code == 200:
    print(f"\n✅ Upload successful!")
    print(f"File URL: https://{bucket_name}-development.zohostratus.in/{object_key}")
else:
    print(f"\n❌ Upload failed.")