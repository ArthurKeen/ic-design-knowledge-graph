from db_utils import get_db

def purge():
    db = get_db()
    collections = [
        "RTL_Module", "RTL_Port", "RTL_Signal", "RTL_LogicChunk", "GitCommit",
        "HAS_PORT", "HAS_SIGNAL", "CONTAINS", "MODIFIED", "DOCUMENTED_BY", 
        "WIRED_TO", "OR1200_Relations", "RESOLVED_TO", "REFERENCES"
    ]
    for col in collections:
        if db.has_collection(col):
            print(f"Truncating collection: {col}")
            db.collection(col).truncate()

if __name__ == "__main__":
    purge()
