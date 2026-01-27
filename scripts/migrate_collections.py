import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from arango import ArangoClient
from config import ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE

SOURCE_DB = os.getenv("ARANGO_SOURCE_DB") or os.getenv("SOURCE_DB")
TARGET_DB = os.getenv("ARANGO_TARGET_DB") or os.getenv("TARGET_DB") or ARANGO_DATABASE

COLLECTIONS_TO_MIGRATE = [
    "OR1200_Documents",
    "OR1200_Chunks", 
    "OR1200_Entities",
    "OR1200_Golden_Entities",
    "OR1200_Relations",
    "OR1200_Golden_Relations",
    "OR1200_Communities",
    # Visualizer System Collections
    "_graphThemeStore",
    "_editor_saved_queries", 
    "_canvasActions",
    "_viewpointActions",
    "_viewpoints"
]

def migrate():
    if not SOURCE_DB or not TARGET_DB:
        print("Error: SOURCE_DB and TARGET_DB must be set via environment variables.")
        print("Set ARANGO_SOURCE_DB and ARANGO_TARGET_DB (or SOURCE_DB/TARGET_DB).")
        return
    print(f"Migrating collections from {SOURCE_DB} to {TARGET_DB}...")
    
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    
    # Check if source DB exists
    sys_db = client.db('_system', username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    if not sys_db.has_database(SOURCE_DB):
        print(f"Error: Source database {SOURCE_DB} does not exist.")
        return
        
    if not sys_db.has_database(TARGET_DB):
        print(f"Error: Target database {TARGET_DB} does not exist.")
        return

    source = client.db(SOURCE_DB, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    target = client.db(TARGET_DB, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)
    
    for col_name in COLLECTIONS_TO_MIGRATE:
        print(f"\nProcessing {col_name}...")
        
        if not source.has_collection(col_name):
            print(f"  Warning: Collection {col_name} not found in source. Skipping.")
            continue
            
        # Create in target if missing
        if not target.has_collection(col_name):
            # Check edge/doc type
            props = source.collection(col_name).properties()
            is_edge = props['type'] == 3
            target.create_collection(col_name, edge=is_edge)
            print(f"  Created collection {col_name} (Edge: {is_edge})")
        else:
            print(f"  Collection {col_name} exists in target. Truncating...")
            target.collection(col_name).truncate()
            
        # Copy data
        source_col = source.collection(col_name)
        target_col = target.collection(col_name)
        
        count = source_col.count()
        print(f"  Copying {count} documents...")
        
        batch = []
        BATCH_SIZE = 1000
        processed = 0
        
        for doc in source_col.all():
            batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                target_col.import_bulk(batch, on_duplicate="replace")
                processed += len(batch)
                print(f"    Imported {processed}/{count}")
                batch = []
                
        if batch:
            target_col.import_bulk(batch, on_duplicate="replace")
            processed += len(batch)
            
        print(f"  ✓ Processed {processed} documents.")

if __name__ == "__main__":
    try:
        migrate()
        print("\nMigration complete!")
    except Exception as e:
        print(f"\nMigration failed: {e}")
        import traceback
        traceback.print_exc()
