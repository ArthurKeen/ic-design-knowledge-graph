import requests
from requests.auth import HTTPBasicAuth
import os
import sys

# Add src to path to import config
sys.path.append(os.path.join(os.getcwd(), "src"))
from config import ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE

def test_connection():
    print(f"Testing connection to {ARANGO_ENDPOINT}...")
    print(f"Mode: {os.getenv('ARANGO_MODE')}")
    
    url = f"{ARANGO_ENDPOINT}/_api/version"
    try:
        response = requests.get(url, auth=HTTPBasicAuth(ARANGO_USERNAME, ARANGO_PASSWORD), timeout=10)
        if response.status_code == 200:
            version = response.json().get('version')
            print(f"Successfully connected! ArangoDB version: {version}")
            return True
        else:
            print(f"Failed to connect. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error connecting: {e}")
        return False

def check_or_create_db():
    print(f"Checking for database '{ARANGO_DATABASE}'...")
    url = f"{ARANGO_ENDPOINT}/_api/database/current"
    # Note: ArangoDB recommends using _system to check/create other DBs
    system_url = f"{ARANGO_ENDPOINT}/_db/_system/_api/database"
    
    try:
        # Check if DB exists
        response = requests.get(system_url, auth=HTTPBasicAuth(ARANGO_USERNAME, ARANGO_PASSWORD))
        if ARANGO_DATABASE in response.json().get('result', []):
            print(f"Database '{ARANGO_DATABASE}' already exists.")
            return True
        
        # Create DB
        print(f"Creating database '{ARANGO_DATABASE}'...")
        payload = {"name": ARANGO_DATABASE}
        create_response = requests.post(system_url, auth=HTTPBasicAuth(ARANGO_USERNAME, ARANGO_PASSWORD), json=payload)
        if create_response.status_code in [201, 200]:
            print(f"Database '{ARANGO_DATABASE}' created successfully.")
            return True
        else:
            print(f"Failed to create database. Status: {create_response.status_code}")
            print(f"Response: {create_response.text}")
            return False
    except Exception as e:
        print(f"Error creating database: {e}")
        return False

if __name__ == "__main__":
    if test_connection():
        check_or_create_db()
