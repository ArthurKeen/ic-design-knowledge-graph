#!/usr/bin/env python3
import sys
import os
import json

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

try:
    from db_utils import get_db
    from config import GRAPHRAG_PREFIX
except ImportError:
    print("Error: Could not import db_utils or config.")
    sys.exit(1)

def check_collections():
    db = get_db()
    
    # Collections from import_all.sh
    doc_cols = [
        "RTL_Module", "RTL_Port", "RTL_Signal", "RTL_LogicChunk", "GitCommit", 
        "FSM_StateMachine", "FSM_State", "RTL_Parameter", "RTL_Memory", 
        "RTL_Function", "RTL_Assign", "RTL_Assertion", "RTL_Always", 
        "ClockDomain", "BusInterface", "MemoryPort", "Operator", "GenerateBlock", "Author"
    ]
    
    edge_cols = [
        "HAS_PORT", "HAS_SIGNAL", "CONTAINS", "MODIFIED", "WIRED_TO", "DEPENDS_ON", 
        "HAS_FSM", "HAS_STATE", "TRANSITIONS_TO", "STATE_REGISTER", "IMPLEMENTED_BY", 
        "HAS_PARAMETER", "USES_PARAMETER", "HAS_MEMORY", "MEMORY_PORT", "STORED_IN", 
        "HAS_FUNCTION", "CALLS_FUNCTION", "FUNCTION_INPUT", "FUNCTION_OUTPUT", 
        "HAS_ASSIGN", "DRIVES", "READS_FROM", "HAS_ASSERTION", "CHECKS_SIGNAL", 
        "HAS_ALWAYS", "SENSITIVE_TO", "CLOCKED_BY", "RESET_BY", "CROSSES_DOMAIN", 
        "PART_OF_BUS", "IMPLEMENTS", "OVERRIDES", "ACCESSES", "USES_OPERATOR", "CALLS",
        "AUTHORED", "MAINTAINS", "RESOLVED_TO", "REFERENCES"
    ]

    # GraphRAG collections
    doc_cols.extend([
        f"{GRAPHRAG_PREFIX}Documents", f"{GRAPHRAG_PREFIX}Golden_Entities", 
        f"{GRAPHRAG_PREFIX}Chunks", f"{GRAPHRAG_PREFIX}Communities", 
        f"{GRAPHRAG_PREFIX}Entities"
    ])
    edge_cols.extend([
        f"{GRAPHRAG_PREFIX}Golden_Relations", f"{GRAPHRAG_PREFIX}Relations", "CONSOLIDATES"
    ])

    results = {
        "empty_docs": [],
        "empty_edges": [],
        "populated": []
    }

    print(f"{'Collection':<40} | {'Count':<10} | {'Status'}")
    print("-" * 65)

    for col_name in doc_cols + edge_cols:
        try:
            if db.has_collection(col_name):
                count = db.collection(col_name).count()
                status = "Populated" if count > 0 else "EMPTY"
                print(f"{col_name:<40} | {count:<10} | {status}")
                
                if count == 0:
                    if col_name in doc_cols:
                        results["empty_docs"].append(col_name)
                    else:
                        results["empty_edges"].append(col_name)
                else:
                    results["populated"].append(col_name)
            else:
                print(f"{col_name:<40} | {'N/A':<10} | MISSING")
                if col_name in doc_cols:
                    results["empty_docs"].append(col_name)
                else:
                    results["empty_edges"].append(col_name)
        except Exception as e:
            print(f"{col_name:<40} | ERROR      | {str(e)[:20]}")

    return results

if __name__ == "__main__":
    check_collections()
