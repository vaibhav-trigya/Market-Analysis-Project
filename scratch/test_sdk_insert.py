import os
import zcatalyst_sdk
from dotenv import load_dotenv

load_dotenv()

# Setup catalyst config
config = {
    'client_id': os.getenv("ZOHO_CLIENT_ID"),
    'client_secret': os.getenv("ZOHO_CLIENT_SECRET"),
    'refresh_token': os.getenv("ZOHO_DATASTORE_REFRESH_TOKEN") or os.getenv("ZOHO_REFRESH_TOKEN"),
    'project_id': os.getenv("PROJECT_ID", "39634000000012090"),
    'type': 'user'
}

# Catalyst SDK initialization
app = zcatalyst_sdk.initialize(config)
datastore = app.datastore()
table = datastore.table('Market_Analysis')

row_data = {
    'record_id': 12345,
    'base_company_name': 'Test'
}

try:
    print("Attempting insert via SDK...")
    res = table.insert_row(row_data)
    print("Success!")
    print(res)
except Exception as e:
    print(f"Error: {e}")
