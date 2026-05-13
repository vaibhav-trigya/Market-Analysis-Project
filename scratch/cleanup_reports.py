import os
import sys
import json
import requests

# Ensure project root is in path
sys.path.append(os.getcwd())
from catalyst_client import catalyst_client

def cleanup_reports():
    print("[*] Starting Reports Index Cleanup...")
    
    # 1. Download existing index
    content = catalyst_client.download_object("reports/index.json")
    if not content:
        print("[-] reports/index.json not found. Nothing to clean.")
        return
    
    try:
        index = json.loads(content)
    except Exception as e:
        print(f"[-] Failed to parse index: {e}")
        return

    print(f"[*] Current index has {len(index)} entries.")
    
    cleaned_index = []
    
    for entry in index:
        original_fname = entry.get("file_name")
        if not original_fname:
            continue
            
        print(f"[*] Checking: {original_fname}...")
        
        # Try to verify existence
        exists = False
        final_key = original_fname
        
        # Variations to try
        variations = [
            original_fname,
            original_fname.lstrip("_"),
            original_fname.replace("__", "_"),
            original_fname.replace("www.", ""),
        ]
        
        # Dedup variations
        variations = list(dict.fromkeys(variations))
        
        for var in variations:
            key = f"reports/{var}"
            # Check if exists by trying to download 1 byte
            url = catalyst_client._object_url(key)
            headers = catalyst_client._auth_headers()
            if not headers: continue
            
            try:
                # Use HEAD or GET with Range to save bandwidth
                resp = requests.get(url, headers={**headers, "Range": "bytes=0-0"}, verify=False, timeout=5)
                if resp.status_code in (200, 206):
                    exists = True
                    final_key = var
                    print(f"  [✓] Found in bucket: {var}")
                    break
            except:
                continue
        
        if exists:
            entry["file_name"] = final_key
            # Clean up the company name in the index too
            if "company_name" in entry:
                # Basic cleaning for display
                cname = entry["company_name"]
                cname = cname.replace("www.", "").replace("https://", "").replace("http://", "")
                entry["company_name"] = cname.split('_Analysis')[0].split('_')[0].split('.')[0].title()
            
            cleaned_index.append(entry)
        else:
            print(f"  [✗] File not found in bucket. Removing from index.")

    # 3. Upload cleaned index
    if cleaned_index != index:
        print(f"[*] Uploading updated index with {len(cleaned_index)} valid entries...")
        catalyst_client.upload_object(
            "reports/index.json",
            json.dumps(cleaned_index, indent=2),
            {"content_type": "application/json"}
        )
        print("[+] Cleanup complete.")
    else:
        print("[*] No changes needed.")

if __name__ == "__main__":
    cleanup_reports()
