import json
import os
from config import (
    DATA_DIR, RTL_NODES_FILE, RTL_EDGES_FILE, DOC_NODES_FILE, 
    GIT_NODES_FILE, GIT_EDGES_FILE, SEMANTIC_EDGES_FILE
)

def split_json_by_type():
    print("Splitting JSON files by type for ArangoDB import...")
    
    # Map CollectionName -> List of Items
    collections = {}
    
    # 1. Process Nodes
    node_files = [RTL_NODES_FILE, DOC_NODES_FILE, GIT_NODES_FILE]
    
    # Add FSM node files if they exist
    import os
    fsm_node_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'fsm_nodes.json')
    fsm_state_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'fsm_state_nodes.json')
    param_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'param_nodes.json')
    memory_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'memory_nodes.json')
    function_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'function_nodes.json')
    assign_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'assign_nodes.json')
    assertion_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'assertion_nodes.json')
    always_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'always_nodes.json')
    clock_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'clock_nodes.json')
    bus_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'bus_nodes.json')
    memory_port_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'memory_port_nodes.json')
    operator_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'operator_nodes.json')
    generate_file = os.path.join(os.path.dirname(RTL_NODES_FILE), 'generate_nodes.json')
    
    if os.path.exists(fsm_node_file):
        node_files.append(fsm_node_file)
    if os.path.exists(fsm_state_file):
        node_files.append(fsm_state_file)
    if os.path.exists(param_file):
        node_files.append(param_file)
    if os.path.exists(memory_file):
        node_files.append(memory_file)
    if os.path.exists(function_file):
        node_files.append(function_file)
    if os.path.exists(assign_file):
        node_files.append(assign_file)
    if os.path.exists(assertion_file):
        node_files.append(assertion_file)
    if os.path.exists(always_file):
        node_files.append(always_file)
    if os.path.exists(clock_file):
        node_files.append(clock_file)
    if os.path.exists(bus_file):
        node_files.append(bus_file)
    if os.path.exists(memory_port_file):
        node_files.append(memory_port_file)
    if os.path.exists(operator_file):
        node_files.append(operator_file)
    if os.path.exists(generate_file):
        node_files.append(generate_file)
    
    for nf in node_files:
        if not os.path.exists(nf):
            continue
        with open(nf, 'r') as f:
            nodes = json.load(f)
            for n in nodes:
                # Sanitization: ArangoDB uses '_key' instead of 'id'. 
                if 'id' in n:
                    n['_key'] = n['id']
                    del n['id']
                
                # Collection Name = n['type']
                ctype = n['type']
                if ctype not in collections:
                    collections[ctype] = []
                collections[ctype].append(n)
                
    # Build ID->Type Map for edge resolution
    id_to_type = {}
    for ctype, items in collections.items():
        for item in items:
            id_to_type[item['_key']] = ctype

    # 2. Process Edges
    edge_files = [RTL_EDGES_FILE, GIT_EDGES_FILE, SEMANTIC_EDGES_FILE]
    
    # Add FSM edge file if it exists
    fsm_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'fsm_edges.json')
    param_mem_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'param_memory_edges.json')
    function_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'function_edges.json')
    assign_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'assign_edges.json')
    assertion_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'assertion_edges.json')
    always_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'always_edges.json')
    clock_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'clock_edges.json')
    bus_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'bus_edges.json')
    memory_access_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'memory_access_edges.json')
    memory_port_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'memory_port_edges.json')
    operator_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'operator_edges.json')
    generate_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'generate_edges.json')
    call_edge_file = os.path.join(os.path.dirname(RTL_EDGES_FILE), 'call_edges.json')
    
    if os.path.exists(fsm_edge_file):
        edge_files.append(fsm_edge_file)
    if os.path.exists(param_mem_edge_file):
        edge_files.append(param_mem_edge_file)
    if os.path.exists(function_edge_file):
        edge_files.append(function_edge_file)
    if os.path.exists(assign_edge_file):
        edge_files.append(assign_edge_file)
    if os.path.exists(assertion_edge_file):
        edge_files.append(assertion_edge_file)
    if os.path.exists(always_edge_file):
        edge_files.append(always_edge_file)
    if os.path.exists(clock_edge_file):
        edge_files.append(clock_edge_file)
    if os.path.exists(bus_edge_file):
        edge_files.append(bus_edge_file)
    if os.path.exists(memory_access_edge_file):
        edge_files.append(memory_access_edge_file)
    if os.path.exists(memory_port_edge_file):
        edge_files.append(memory_port_edge_file)
    if os.path.exists(operator_edge_file):
        edge_files.append(operator_edge_file)
    if os.path.exists(generate_edge_file):
        edge_files.append(generate_edge_file)
    if os.path.exists(call_edge_file):
        edge_files.append(call_edge_file)
    
    for ef in edge_files:
        if not os.path.exists(ef):
            continue
        with open(ef, 'r') as f:
            edges = json.load(f)
            for e in edges:
                etype = e.get('type')
                if not etype:
                    continue
                
                src_id = e.get('from')
                dst_id = e.get('to')
                
                if not src_id or not dst_id:
                    # Might already be processed or in _from/_to format
                    continue
                
                if src_id not in id_to_type or dst_id not in id_to_type:
                    print(f"Warning: Edge {etype} connects unknown node(s): {src_id}->{dst_id}")
                    continue
                
                src_type = id_to_type[src_id]
                dst_type = id_to_type[dst_id]
                
                e['_from'] = f"{src_type}/{src_id}"
                e['_to'] = f"{dst_type}/{dst_id}"
                
                # If the edge has a deterministic _key, keep it
                if '_key' in e:
                    # ArangoImport will pick it up
                    pass
                
                # cleanup
                if 'from' in e: del e['from']
                if 'to' in e: del e['to']
                
                if etype not in collections:
                    collections[etype] = []
                collections[etype].append(e)

    # Write output files
    generated_files = []
    for cname, items in collections.items():
        # Deduplication: Ensure unique _key per collection
        unique_items = {}
        for item in items:
            key = item.get('_key')
            if key:
                if key not in unique_items:
                    unique_items[key] = item
                else:
                    # Merge metadata if needed, or just keep first (most specific)
                    pass
            else:
                # Items without keys (shouldn't happen with our ETL)
                unique_items[id(item)] = item
        
        final_items = list(unique_items.values())
        
        # Filename: import_CollectionName.json
        fname = f"import_{cname}.json"
        fpath = os.path.join(DATA_DIR, fname)
        with open(fpath, 'w') as f:
            json.dump(final_items, f, indent=2)
        generated_files.append(cname)
        print(f"Prepared {cname}: {len(final_items)} items -> {fname} (Deduplicated from {len(items)})")
        
    return generated_files

if __name__ == "__main__":
    split_json_by_type()
