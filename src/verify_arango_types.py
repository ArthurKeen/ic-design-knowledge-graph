import requests
from requests.auth import HTTPBasicAuth
import os
import sys

# Add src to path to import config
sys.path.append(os.path.join(os.getcwd(), "src"))
from config import ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE

def verify_types():
    print(f"Verifying collection types on {ARANGO_ENDPOINT}...")
    url = f"{ARANGO_ENDPOINT}/_db/{ARANGO_DATABASE}/_api/collection"
    
    try:
        response = requests.get(url, auth=HTTPBasicAuth(ARANGO_USERNAME, ARANGO_PASSWORD))
        if response.status_code == 200:
            collections = response.json().get('result', [])
            print(f"{'Collection':<20} | {'Type':<10}")
            print("-" * 35)
            for col in collections:
                if col['name'].startswith('_'): continue
                # type 2 = Document, type 3 = Edge
                ctype = "Document" if col['type'] == 2 else "Edge"
                print(f"{col['name']:<20} | {ctype:<10}")
            return True
        else:
            print(f"Failed. Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    verify_types()
