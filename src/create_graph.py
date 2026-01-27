import requests
import os
import sys
import json

# Add src to path to import config
sys.path.append(os.path.join(os.getcwd(), "src"))
from config import (
    GRAPH_NAME, COL_MODULE, COL_PORT, COL_SIGNAL, COL_LOGIC, COL_COMMIT,
    COL_DOCS, COL_ENTITIES, COL_CHUNKS, COL_RELATIONS, COL_COMMUNITIES,
    COL_RAW_ENTITIES, COL_RAW_RELATIONS,
    COL_FSM, COL_FSM_STATE, COL_PARAMETER, COL_MEMORY, COL_FUNCTION, COL_ASSIGN, COL_ASSERTION, COL_ALWAYS,
    COL_CLOCK, COL_BUS, COL_MEMORY_PORT, COL_OPERATOR, COL_GENERATE,
    EDGE_CONTAINS, EDGE_HAS_PORT, EDGE_HAS_SIGNAL, EDGE_MODIFIED,
    EDGE_RESOLVED, EDGE_REFERENCES, EDGE_WIRED_TO, EDGE_DEPENDS_ON, EDGE_OVERRIDES,
    EDGE_HAS_FSM, EDGE_HAS_STATE, EDGE_TRANSITIONS_TO, EDGE_STATE_REGISTER,
    EDGE_IMPLEMENTED_BY,
    EDGE_HAS_PARAMETER, EDGE_USES_PARAMETER, EDGE_HAS_MEMORY, EDGE_MEMORY_PORT,
    EDGE_STORED_IN,
    EDGE_HAS_FUNCTION, EDGE_CALLS_FUNCTION, EDGE_FUNCTION_INPUT, EDGE_FUNCTION_OUTPUT,
    EDGE_HAS_ASSIGN, EDGE_DRIVES, EDGE_READS_FROM,
    EDGE_HAS_ASSERTION, EDGE_CHECKS_SIGNAL,
    EDGE_HAS_ALWAYS, EDGE_SENSITIVE_TO, EDGE_CLOCKED_BY, EDGE_RESET_BY,
    EDGE_CROSSES_DOMAIN, EDGE_IMPLEMENTS, EDGE_PART_OF_BUS, EDGE_ACCESSES, EDGE_CALLS,
    EDGE_HAS_OPERATOR, EDGE_USES_OPERATOR,
    GRAPHRAG_PREFIX
)

# New collection for consolidation breadcrumbs
COL_CONSOLIDATES = "CONSOLIDATES"
# Author expertise mapping collections
COL_AUTHOR = "Author"
EDGE_AUTHORED = "AUTHORED"
EDGE_MAINTAINS = "MAINTAINS"
from db_utils import get_requests_auth, get_api_url

def create_graph():
    print(f"Creating/Updating graph '{GRAPH_NAME}'...")
    
    # Graph API Endpoint
    url = get_api_url("gharial")
    
    # Edge Definitions
    edge_definitions = [
        {
            "collection": EDGE_CONTAINS,
            "from": [COL_MODULE],
            "to": [COL_MODULE, COL_LOGIC, COL_GENERATE]
        },
        {
            "collection": EDGE_HAS_PORT,
            "from": [COL_MODULE],
            "to": [COL_PORT]
        },
        {
            "collection": EDGE_HAS_SIGNAL,
            "from": [COL_MODULE],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_MODIFIED,
            "from": [COL_COMMIT],
            "to": [COL_MODULE]
        },
        {
            "collection": EDGE_RESOLVED,
            "from": [COL_MODULE, COL_PORT, COL_SIGNAL],
            "to": [COL_ENTITIES]
        },
        {
            "collection": EDGE_REFERENCES,
            "from": [COL_LOGIC],
            "to": [COL_CHUNKS]
        },
        {
            "collection": COL_RELATIONS,
            "from": [COL_CHUNKS, COL_ENTITIES, COL_DOCS, COL_COMMUNITIES],
            "to": [COL_CHUNKS, COL_ENTITIES, COL_DOCS, COL_COMMUNITIES]
        },
        {
            "collection": COL_RAW_RELATIONS,
            "from": [COL_CHUNKS, COL_RAW_ENTITIES, COL_DOCS, COL_COMMUNITIES],
            "to": [COL_CHUNKS, COL_RAW_ENTITIES, COL_DOCS, COL_COMMUNITIES]
        },
        {
            "collection": EDGE_WIRED_TO,
            "from": [COL_PORT],
            "to": [COL_PORT]
        },
        {
            "collection": EDGE_OVERRIDES,
            "from": [COL_MODULE],
            "to": [COL_PARAMETER]
        },
        {
            "collection": EDGE_DEPENDS_ON,
            "from": [COL_MODULE],
            "to": [COL_MODULE]
        },
        {
            "collection": COL_CONSOLIDATES,
            "from": [COL_ENTITIES],
            "to": [COL_RAW_ENTITIES]
        },
        {
            "collection": EDGE_AUTHORED,
            "from": [COL_AUTHOR],
            "to": [COL_COMMIT]
        },
        {
            "collection": EDGE_MAINTAINS,
            "from": [COL_AUTHOR],
            "to": [COL_MODULE]
        },
        {
            "collection": EDGE_HAS_FSM,
            "from": [COL_MODULE],
            "to": [COL_FSM]
        },
        {
            "collection": EDGE_HAS_STATE,
            "from": [COL_FSM],
            "to": [COL_FSM_STATE]
        },
        {
            "collection": EDGE_TRANSITIONS_TO,
            "from": [COL_FSM_STATE],
            "to": [COL_FSM_STATE]
        },
        {
            "collection": EDGE_STATE_REGISTER,
            "from": [COL_FSM],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_IMPLEMENTED_BY,
            "from": [COL_FSM],
            "to": [COL_LOGIC]
        },
        {
            "collection": EDGE_HAS_PARAMETER,
            "from": [COL_MODULE],
            "to": [COL_PARAMETER]
        },
        {
            "collection": EDGE_USES_PARAMETER,
            "from": [COL_SIGNAL, COL_PORT, COL_MEMORY],
            "to": [COL_PARAMETER]
        },
        {
            "collection": EDGE_HAS_MEMORY,
            "from": [COL_MODULE],
            "to": [COL_MEMORY]
        },
        {
            "collection": EDGE_MEMORY_PORT,
            "from": [COL_MEMORY],
            "to": [COL_PORT]
        },
        {
            "collection": EDGE_STORED_IN,
            "from": [COL_SIGNAL],
            "to": [COL_MEMORY]
        },
        {
            "collection": EDGE_HAS_FUNCTION,
            "from": [COL_MODULE],
            "to": [COL_FUNCTION]
        },
        {
            "collection": EDGE_CALLS_FUNCTION,
            "from": [COL_LOGIC, COL_FUNCTION],
            "to": [COL_FUNCTION]
        },
        {
            "collection": EDGE_FUNCTION_INPUT,
            "from": [COL_FUNCTION],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_FUNCTION_OUTPUT,
            "from": [COL_FUNCTION],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_HAS_ASSIGN,
            "from": [COL_MODULE],
            "to": [COL_ASSIGN]
        },
        {
            "collection": EDGE_DRIVES,
            "from": [COL_ASSIGN],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_READS_FROM,
            "from": [COL_ASSIGN],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_HAS_ASSERTION,
            "from": [COL_MODULE],
            "to": [COL_ASSERTION]
        },
        {
            "collection": EDGE_CHECKS_SIGNAL,
            "from": [COL_ASSERTION],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_HAS_ALWAYS,
            "from": [COL_MODULE],
            "to": [COL_ALWAYS]
        },
        {
            "collection": EDGE_SENSITIVE_TO,
            "from": [COL_ALWAYS],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_RESET_BY,
            "from": [COL_ALWAYS],
            "to": [COL_SIGNAL]
        },
        {
            "collection": EDGE_CLOCKED_BY,
            "from": [COL_MODULE, COL_SIGNAL, COL_ALWAYS],
            "to": [COL_CLOCK]
        },
        {
            "collection": EDGE_CROSSES_DOMAIN,
            "from": [COL_SIGNAL],
            "to": [COL_CLOCK]
        },
        {
            "collection": EDGE_IMPLEMENTS,
            "from": [COL_MODULE],
            "to": [COL_BUS]
        },
        {
            "collection": EDGE_PART_OF_BUS,
            "from": [COL_PORT, COL_SIGNAL],
            "to": [COL_BUS, COL_MEMORY_PORT]
        },
        {
            "collection": EDGE_ACCESSES,
            "from": [COL_LOGIC],
            "to": [COL_MEMORY]
        },
        {
            "collection": EDGE_CALLS,
            "from": [COL_LOGIC, COL_FUNCTION],
            "to": [COL_FUNCTION]
        },
        {
            "collection": EDGE_HAS_OPERATOR,
            "from": [COL_MODULE],
            "to": [COL_OPERATOR]
        },
        {
            "collection": EDGE_USES_OPERATOR,
            "from": [COL_LOGIC, COL_SIGNAL],
            "to": [COL_OPERATOR]
        }
    ]
    
    graph_data = {
        "name": GRAPH_NAME,
        "edgeDefinitions": edge_definitions
    }
    
    auth = get_requests_auth()
    
    try:
        # Check if our graph exists
        check_url = f"{url}/{GRAPH_NAME}"
        response = requests.get(check_url, auth=auth)
        
        if response.status_code == 200:
            print(f"Graph '{GRAPH_NAME}' already exists. Re-creating to update definitions...")
            # dropCollections=false is the default for Gharial, but we are explicit here for safety
            requests.delete(f"{check_url}?dropCollections=false", auth=auth)
            
        # Also check for the existing GraphRAG graph which might be using the same edge collections
        conflict_graph = f"{GRAPHRAG_PREFIX}kg"
        conflict_url = f"{url}/{conflict_graph}"
        conflict_response = requests.get(conflict_url, auth=auth)
        if conflict_response.status_code == 200:
            print(f"Graph '{conflict_graph}' found. Deleting to avoid edge collection conflicts...")
            requests.delete(f"{conflict_url}?dropCollections=false", auth=auth)
        
        # Create Graph
        create_response = requests.post(url, auth=auth, json=graph_data)
        if create_response.status_code in [201, 202]:
            print(f"Successfully created graph '{GRAPH_NAME}'!")
            return True
        else:
            print(f"Failed to create graph. Status: {create_response.status_code}")
            print(f"Response: {create_response.text}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    create_graph()
