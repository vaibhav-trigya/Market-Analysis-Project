import os
import json
from catalyst_client import catalyst_client

def list_bucket_reports():
    print("Listing reports in bucket...")
    reports = catalyst_client._list_objects(prefix="reports/")
    print(f"Found {len(reports)} objects in reports/")
    for obj in reports:
        print(f" - {obj.get('key') or obj.get('object_name')}")

    print("\nReading reports/index.json...")
    content = catalyst_client.download_object("reports/index.json")
    if content:
        index = json.loads(content)
        print(f"Index has {len(index)} entries.")
        for entry in index[:10]:
            print(f" - {entry.get('file_name')}")
    else:
        print("index.json not found.")

if __name__ == "__main__":
    list_bucket_reports()
