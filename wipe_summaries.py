import os
import json

OUTPUT_DIR = "scraped_data"

def wipe_summaries():
    print(f"[*] Wiping all 'analysis_summary' fields in {OUTPUT_DIR}...")
    count = 0
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in files:
            if f.endswith(".json"):
                file_path = os.path.join(root, f)
                try:
                    with open(file_path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                    
                    if "analysis_summary" in data:
                        del data["analysis_summary"]
                        with open(file_path, "w", encoding="utf-8") as file:
                            json.dump(data, file, indent=2)
                        count += 1
                except Exception as e:
                    print(f"[-] Error processing {f}: {e}")
    
    print(f"[+] Successfully wiped {count} summaries. Your next report generation will force a fresh, neutral AI analysis.")

if __name__ == "__main__":
    wipe_summaries()
