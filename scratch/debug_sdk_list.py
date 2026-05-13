import os
import zcatalyst_sdk
from dotenv import load_dotenv

load_dotenv()

def debug_sdk_list():
    # Set env variables for SDK
    os.environ["CATALYST_PROJECT_ID"] = os.getenv("PROJECT_ID", "39634000000012090")
    os.environ["CATALYST_CLIENT_ID"] = os.getenv("ZOHO_CLIENT_ID")
    os.environ["CATALYST_CLIENT_SECRET"] = os.getenv("ZOHO_CLIENT_SECRET")
    os.environ["CATALYST_REFRESH_TOKEN"] = os.getenv("ZOHO_REFRESH_TOKEN")
    
    try:
        # Initialize
        app = zcatalyst_sdk.initialize()
        stratus = app.stratus()
        bucket = stratus.bucket("test-scrapper")
        
        print("[*] Listing objects via SDK (env-auth)...")
        objects = bucket.get_objects()
        
        print(f"[+] SDK returned {len(objects)} objects:")
        for obj in objects:
            # Note: in Python SDK FileObject has get_object_name()
            print(f"  - Name: {obj.get_object_name()}, Size: {obj.get_size()}")
            
    except Exception as e:
        print(f"[!] SDK Error: {e}")

if __name__ == "__main__":
    debug_sdk_list()
