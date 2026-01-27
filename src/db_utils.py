import requests
from requests.auth import HTTPBasicAuth
from arango import ArangoClient
from config import ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE

def get_arango_client():
    """Returns an ArangoDB client instance."""
    return ArangoClient(hosts=ARANGO_ENDPOINT)

def get_db():
    """Returns an ArangoDB database instance."""
    client = get_arango_client()
    return client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)

def get_system_db():
    """Returns an ArangoDB system database instance."""
    client = get_arango_client()
    return client.db('_system', username=ARANGO_USERNAME, password=ARANGO_PASSWORD)

def get_requests_auth():
    """Returns HTTPBasicAuth for requests."""
    return HTTPBasicAuth(ARANGO_USERNAME, ARANGO_PASSWORD)

def get_api_url(path=""):
    """Constructs an ArangoDB API URL."""
    base = f"{ARANGO_ENDPOINT}/_db/{ARANGO_DATABASE}/_api"
    if path:
        return f"{base}/{path.lstrip('/')}"
    return base
