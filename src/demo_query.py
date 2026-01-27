import json
from config import RTL_NODES_FILE, RTL_EDGES_FILE, DOC_NODES_FILE, GIT_NODES_FILE, GIT_EDGES_FILE, SEMANTIC_EDGES_FILE

def load_graph():
    print("Loading Graph Data...")
    graph = {"nodes": {}, "edges": []}
    
    # Load Nodes
    for fpath in [RTL_NODES_FILE, DOC_NODES_FILE, GIT_NODES_FILE]:
        with open(fpath, 'r') as f:
            nodes = json.load(f)
            for n in nodes:
                graph["nodes"][n['id']] = n

    # Load Edges
    for fpath in [RTL_EDGES_FILE, GIT_EDGES_FILE, SEMANTIC_EDGES_FILE]:
        with open(fpath, 'r') as f:
            edges = json.load(f)
            graph["edges"].extend(edges)
            
    print(f"Graph Loaded: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges.")
    return graph

def demo_queries(graph):
    print("\n--- Running Demo Queries ---\n")
    
    # helper: find edges from node
    def get_out_edges(node_id, edge_type=None):
        return [e for e in graph['edges'] if e['from'] == node_id and (edge_type is None or e['type'] == edge_type)]

    def get_in_edges(node_id, edge_type=None):
        return [e for e in graph['edges'] if e['to'] == node_id and (edge_type is None or e['type'] == edge_type)]

    # Query 1: The Semantic Bridge
    # "Find documentation for 'or1200_cpu'"
    target_module = "or1200_cpu"
    print(f"Query 1: Find documentation for '{target_module}'")
    
    if target_module in graph["nodes"]:
        docs_edges = get_out_edges(target_module, "DOCUMENTED_BY")
        if docs_edges:
            for e in docs_edges:
                doc_id = e['to']
                doc_node = graph["nodes"].get(doc_id)
                print(f"  [MATCH] Found Spec Section: '{doc_node['label']}' (Score: {e['metadata']['score']})")
                print(f"     -> Excerpt: {doc_node['metadata']['text'][:100]}...")
        else:
            print("  [No Link found]")
    else:
        print(f"  Module {target_module} not found!")

    # Query 2: Time Travel / Impact Analysis
    # "Show me which spec sections might be affected by recent commits"
    print("\nQuery 2: Impact Analysis (Recent Commits -> Code -> Docs)")
    
    # Get last 3 commits
    commits = [n for n in graph["nodes"].values() if n['type'] == "GitCommit"]
    commits.sort(key=lambda x: x['metadata']['timestamp'], reverse=True)
    recent_commits = commits[:3]
    
    for commit in recent_commits:
        print(f"\n  Commit: {commit['id'][:7]} by {commit['metadata']['author']}")
        # Find modified files
        mod_edges = get_out_edges(commit['id'], "MODIFIED")
        for me in mod_edges:
            rtl_id = me['to']
            rtl_node = graph['nodes'].get(rtl_id)
            if rtl_node:
                print(f"    -> Modified Module: {rtl_node['label']}")
                # Traverse to Docs
                doc_edges = get_out_edges(rtl_id, "DOCUMENTED_BY")
                if doc_edges:
                    for de in doc_edges:
                        doc_node = graph['nodes'].get(de['to'])
                        print(f"       -> [ALERT] Creates potential drift in Spec: '{doc_node['label']}'")
                else:
                     print(f"       -> (No semantic link to specs found)")

if __name__ == "__main__":
    g = load_graph()
    demo_queries(g)
