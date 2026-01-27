import os
import json
import subprocess
import hashlib
from config import (
    GIT_DIR, GIT_NODES_FILE, GIT_EDGES_FILE, RTL_NODES_FILE,
    COL_MODULE, COL_COMMIT, EDGE_MODIFIED
)

def extract_git_history():
    print(f"Extracting Git history from: {GIT_DIR}")
    
    # Check if rtl_nodes exists to build a map
    file_to_module = {}
    if os.path.exists(RTL_NODES_FILE):
        with open(RTL_NODES_FILE, 'r') as f:
            rtl_nodes = json.load(f)
            for node in rtl_nodes:
                if node['type'] == COL_MODULE and 'file' in node['metadata']:
                    # Map 'or1200_alu.v' -> 'or1200_alu'
                    fname = os.path.basename(node['metadata']['file'])
                    file_to_module[fname] = node['id']
                    
    # Run git log
    cmd = ["git", "log", "--name-only", "--pretty=format:COMMIT:%H|%an|%at"]
    
    try:
        result = subprocess.run(cmd, cwd=GIT_DIR, capture_output=True, text=True, errors='replace')
    except Exception as e:
        print(f"Error running git log: {e}")
        return

    lines = result.stdout.splitlines()
    
    commits = []
    edges = []
    
    current_commit = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("COMMIT:"):
            # New commit
            parts = line[7:].split('|')
            if len(parts) >= 3:
                c_hash = parts[0]
                c_author = parts[1]
                c_ts = int(parts[2])
                
                current_commit = {
                    "id": c_hash,
                    "label": f"Commit {c_hash[:7]}",
                    "type": COL_COMMIT,
                    "metadata": {
                        "author": c_author,
                        "timestamp": c_ts
                    }
                }
                commits.append(current_commit)
        else:
            # It's a file
            if current_commit:
                fname = os.path.basename(line)
                
                # Check if this file maps to a known RTL module
                if fname in file_to_module:
                    module_id = file_to_module[fname]
                    
                    edge_key = hashlib.md5(f"{current_commit['id']}:{module_id}:MODIFIED".encode()).hexdigest()
                    edges.append({
                        "_key": edge_key,
                        "from": current_commit['id'],
                        "to": module_id,
                        "type": EDGE_MODIFIED,
                        "metadata": {
                            "timestamp": current_commit['metadata']['timestamp'],
                            "file_path": line
                        }
                    })

    # Save
    with open(GIT_NODES_FILE, 'w') as f:
        json.dump(commits, f, indent=2)
        
    with open(GIT_EDGES_FILE, 'w') as f:
        json.dump(edges, f, indent=2)
        
    print(f"Git Extraction Complete. {len(commits)} commits, {len(edges)} modified edges.")

if __name__ == "__main__":
    extract_git_history()
