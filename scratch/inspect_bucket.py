import os
import json
from catalyst_client import catalyst_client
from dotenv import load_dotenv

load_dotenv()

print("--- STRATUS BUCKET INSPECTOR ---")
print(f"Bucket: {catalyst_client.bucket_name}")

# List everything
try:
    objects = catalyst_client._list_objects(prefix="")
    if not objects:
        print("[-] No objects found in the bucket.")
    else:
        print(f"[+] Found {len(objects)} objects:")
        for obj in objects:
            print(f"  - {obj.get('name') or obj.get('key')}")
            
    # Try listing partners specifically
    partners = catalyst_client.list_partners()
    print(f"\n[+] list_partners() returned {len(partners)} records.")
    for p in partners:
        print(f"  - Partner: {p.get('name')} (Parent: {p.get('parent_company')})")

except Exception as e:
    print(f"[!] Error during inspection: {e}")
