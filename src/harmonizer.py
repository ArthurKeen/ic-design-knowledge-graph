import json
import re
from config import RTL_NODES_FILE, DOC_NODES_FILE, SEMANTIC_EDGES_FILE

def harmonize():
    print("Harmonizing RTL and Docs...")
    
    with open(RTL_NODES_FILE, 'r') as f:
        rtl_nodes = json.load(f)
        
    with open(DOC_NODES_FILE, 'r') as f:
        doc_nodes = json.load(f)
        
    edges = []
    
    # Simple strategy: If Module Name appears in Doc Chunk text -> Link
    
    # optimization: compile regex for each module?
    # or just brute force since size is small (76 modules * 122 docs = 9272 checks - trivial)
    
    # Filter only Module nodes
    modules = [n for n in rtl_nodes if n['type'] == 'RTL_Module']
    
    for mod in modules:
        mod_name = mod['id']
        # Also clean name: or1200_alu -> alu ?
        # Be careful, "alu" is common. "or1200_alu" is specific.
        # "or1200_cpu" -> "CPU" ?
        # Let's try matching the full name 'or1200_xxxx' and also 'xxxx' if it's > 3 chars
        
        candidates = {mod_name}
        if mod_name.startswith("or1200_"):
            short_name = mod_name[7:]
            if len(short_name) >= 3:
                candidates.add(short_name)
        
        for doc in doc_nodes:
            text = doc['metadata']['text'].lower()
            title = doc['label'].lower()
            
            score = 0
            matched_term = ""
            
            for term in candidates:
                # whole word match preferable
                # regex \bterm\b
                if re.search(r'\b' + re.escape(term) + r'\b', text) or re.search(r'\b' + re.escape(term) + r'\b', title):
                    score += 1
                    matched_term = term
            
            if score > 0:
                edges.append({
                    "from": mod['id'],
                    "to": doc['id'],
                    "type": "DOCUMENTED_BY",
                    "metadata": {
                        "matched_term": matched_term,
                        "score": score
                    }
                })
                
    with open(SEMANTIC_EDGES_FILE, 'w') as f:
        json.dump(edges, f, indent=2)
        
    print(f"Harmonization Complete. Created {len(edges)} semantic links.")

if __name__ == "__main__":
    harmonize()
