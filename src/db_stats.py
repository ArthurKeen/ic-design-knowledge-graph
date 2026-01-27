import csv
import json
import sys
import os
from arango import ArangoClient
from dotenv import load_dotenv

# Add src to path to import config
sys.path.append(os.path.join(os.getcwd(), "src"))
from config import ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE

def get_doc_size_no_system(doc):
    """Calculate the size of a document excluding properties starting with '_'."""
    filtered_doc = {k: v for k, v in doc.items() if not k.startswith('_')}
    return len(json.dumps(filtered_doc).encode('utf-8'))

def generate_db_stats(output_file="data/db_collection_stats.csv"):
    # Load connection details
    load_dotenv()
    
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    db = client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)

    stats = []
    total_vertex_count = 0
    total_edge_count = 0

    print(f"Analyzing collections in database: {ARANGO_DATABASE}...")

    collections = db.collections()
    for col in collections:
        if col['system']:
            continue

        name = col['name']
        col_type = "Edge" if col['type'] == 'edge' else "Vertex"
        
        # Get count
        count = db.collection(name).count()
        
        # Sample for size calculation
        avg_size = 0
        if count > 0:
            # Sample up to 20 documents
            sample_limit = min(count, 20)
            cursor = db.aql.execute(f"FOR d IN {name} LIMIT @limit RETURN d", bind_vars={'limit': sample_limit})
            samples = list(cursor)
            
            if samples:
                total_sample_size = sum(get_doc_size_no_system(s) for s in samples)
                avg_size = total_sample_size / len(samples)

        stats.append({
            "Collection Name": name,
            "Collection Type": col_type,
            "Count": count,
            "Avg Doc Size (Bytes)": round(avg_size, 2)
        })

        if col_type == "Vertex":
            total_vertex_count += count
        else:
            total_edge_count += count

    # Add totals
    stats.append({
        "Collection Name": "TOTAL",
        "Collection Type": "Vertex Total",
        "Count": total_vertex_count,
        "Avg Doc Size (Bytes)": ""
    })
    stats.append({
        "Collection Name": "TOTAL",
        "Collection Type": "Edge Total",
        "Count": total_edge_count,
        "Avg Doc Size (Bytes)": ""
    })

    # Write to CSV
    keys = stats[0].keys()
    with open(output_file, 'w', newline='') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(stats)

    print(f"\nStats successfully written to {output_file}")
    
    # Print a preview table to terminal
    print("\n" + "="*80)
    print(f"{'Collection Name':<40} | {'Type':<10} | {'Count':<10} | {'Avg Size (B)':<10}")
    print("-" * 80)
    for row in stats:
        if row['Collection Name'] == "TOTAL":
            print("-" * 80)
        print(f"{row['Collection Name']:<40} | {row['Collection Type']:<10} | {row['Count']:<10} | {row['Avg Doc Size (Bytes)']:<10}")
    print("="*80)

if __name__ == "__main__":
    generate_db_stats()
