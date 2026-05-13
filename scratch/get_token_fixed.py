import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("ZOHO_CLIENT_ID")
client_secret = os.getenv("ZOHO_CLIENT_SECRET")

def generate():
    auth_code = "1000.46a9e1b16f9c3c75286126c65f7fce50.35f90a47a6088ea58151f9991a7dac95"
    url = "https://accounts.zoho.in/oauth/v2/token"
    params = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code
    }

    print(f"[*] Requesting tokens for code: {auth_code[:10]}...")
    resp = requests.post(url, params=params)
    print(resp.json())

if __name__ == "__main__":
    generate()
