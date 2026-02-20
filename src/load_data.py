import os
import sys
import json

# Add repo root to path so we can import src.*
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.db_utils import get_db
from src.config import DATA_DIR

def load_nodes(db, filepath, id_map):
    """Load nodes and populate id_map (id -> collection)."""
    if not os.path.exists(filepath):
        print(f"  Warning: File not found: {filepath}")
        return

    print(f"  Loading Nodes from {os.path.basename(filepath)}...")
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"  Error: Invalid JSON in {filepath}")
        return

    if not data:
        return

    grouped = {}
    for item in data:
        col_name = item.get('type')
        if not col_name: continue
        
        # Populate ID map
        item_id = item.get('id')
        if item_id:
            id_map[item_id] = col_name
            
        if col_name not in grouped:
            grouped[col_name] = []
        grouped[col_name].append(item)
        
    for col_name, docs in grouped.items():
        if not db.has_collection(col_name):
            print(f"    Creating collection: {col_name}")
            db.create_collection(col_name)
        
        col = db.collection(col_name)
        col.truncate() # Clean slate
        
        # Ensure _key is set to id to maintain graph integrity
        for doc in docs:
            if 'id' in doc:
                doc['_key'] = doc['id']
                
        BATCH_SIZE = 1000
        total = len(docs)
        imported = 0
        for i in range(0, total, BATCH_SIZE):
            try:
                col.import_bulk(docs[i:i+BATCH_SIZE], on_duplicate="replace")
                imported += len(docs[i:i+BATCH_SIZE])
            except Exception as e:
                print(f"    Error importing batch {col_name}: {e}")
        print(f"    ✓ {col_name}: {imported}/{total}")

def load_edges(db, filepath, id_map):
    """Load edges, resolving _from and _to using id_map."""
    if not os.path.exists(filepath):
        print(f"  Warning: File not found: {filepath}")
        return

    print(f"  Loading Edges from {os.path.basename(filepath)}...")
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except:
        return

    grouped = {}
    for item in data:
        col_name = item.get('type')
        if not col_name: continue
        
        # Fix _from / _to
        src_id = item.get('from')
        dst_id = item.get('to')
        
        if src_id in id_map and dst_id in id_map:
            item['_from'] = f"{id_map[src_id]}/{src_id}"
            item['_to'] = f"{id_map[dst_id]}/{dst_id}"
            
            # Remove old keys to avoid confusion (optional, but cleaner)
            # item.pop('from', None)
            # item.pop('to', None)
            
            if col_name not in grouped:
                grouped[col_name] = []
            grouped[col_name].append(item)
        else:
            # print(f"    Warning: Could not resolve edge {src_id} -> {dst_id}")
            pass
            
    for col_name, docs in grouped.items():
        if not db.has_collection(col_name):
            print(f"    Creating edge collection: {col_name}")
            db.create_collection(col_name, edge=True)
            
        col = db.collection(col_name)
        # Ensure idempotency for re-runs
        try:
            col.truncate()
        except Exception:
            pass
        BATCH_SIZE = 1000
        total = len(docs)
        imported = 0
        for i in range(0, total, BATCH_SIZE):
            try:
                col.import_bulk(docs[i:i+BATCH_SIZE], on_duplicate="replace")
                imported += len(docs[i:i+BATCH_SIZE])
            except Exception as e:
                print(f"    Error importing batch {col_name}: {e}")
        print(f"    ✓ {col_name}: {imported}/{total}")

def main():
    print("="*60)
    print("Loading ETL Data with ID Resolution")
    print("="*60)
    
    try:
        db = get_db()
        print(f"Connected to: {db.name}\n")
        
        # 1. Load Nodes and build ID Map
        id_map = {} # id -> collection_name

        # Dynamically discover all generated node files
        node_files = sorted(
            [
                os.path.join(DATA_DIR, f)
                for f in os.listdir(DATA_DIR)
                if f.endswith("_nodes.json")
            ]
        )
        if not node_files:
            print(f"[ERROR] No *_nodes.json files found in {DATA_DIR}")
            sys.exit(1)

        for nf in node_files:
            load_nodes(db, nf, id_map)
        
        print(f"\nID Map built: {len(id_map)} entries")
        
        # 2. Load Edges using Map
        edge_files = sorted(
            [
                os.path.join(DATA_DIR, f)
                for f in os.listdir(DATA_DIR)
                if f.endswith("_edges.json")
            ]
        )
        if not edge_files:
            print(f"[WARN] No *_edges.json files found in {DATA_DIR}")

        for ef in edge_files:
            load_edges(db, ef, id_map)
        
        print("\n" + "="*60)
        print("Data Loading Complete!")
        print("="*60)
        
    except Exception as e:
        print(f"\n[ERROR] Loading failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
