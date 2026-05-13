import os
import zcatalyst_sdk
import requests
from dotenv import load_dotenv

load_dotenv()

# SNEAKY: Monkeypatch requests.get to see where the SDK is calling
original_get = requests.get
def spy_get(url, *args, **kwargs):
    print(f"\n[SDK SPY] The SDK is calling this URL: {url}")
    return original_get(url, *args, **kwargs)

requests.get = spy_get

# Initialize SDK
config = {
    "project_id": os.getenv("PROJECT_ID"),
    "client_id": os.getenv("ZOHO_CLIENT_ID"),
    "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
    "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
    "environment": os.getenv("CATALYST_ENVIRONMENT")
}

print("--- INITIALIZING SDK SPY ---")
app = zcatalyst_sdk.initialize(config)
stratus = app.stratus()
bucket = stratus.bucket(os.getenv("STRATUS_BUCKET"))

try:
    print("[*] Asking SDK to list objects...")
    # This will trigger the spy_get
    bucket.list_objects()
except Exception as e:
    print(f"[*] SDK Call finished (might fail but we want the URL): {e}")
