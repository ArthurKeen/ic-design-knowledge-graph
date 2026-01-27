#!/usr/bin/env python3
"""
RTL Task and Function Call Analysis

Identifies calls to Verilog functions and tasks from logic chunks 
(always blocks, assignments) and other functions.
"""

import os
import re
import json
import hashlib
from typing import List, Dict, Tuple, Set

def get_edge_key(from_id, to_id, edge_type):
    """Generate deterministic key for edges"""
    raw = f"{from_id}:{to_id}:{edge_type}"
    return hashlib.md5(raw.encode()).hexdigest()

def sanitize_id(raw_id):
    """Sanitize ID for ArangoDB _key requirements"""
    clean = re.sub(r'[\s\t\n\r]+', '', raw_id)
    clean = re.sub(r'[^a-zA-Z0-9_\-:\.]', '_', clean)
    return clean.strip('_')

def analyze_calls(data_dir: str):
    print("="*60)
    print("Function/Task Call Analysis Starting...")
    print("="*60)

    function_nodes_file = os.path.join(data_dir, 'function_nodes.json')
    rtl_nodes_file = os.path.join(data_dir, 'rtl_nodes.json')

    if not os.path.exists(function_nodes_file) or not os.path.exists(rtl_nodes_file):
        print("Required data files not found.")
        return

    with open(function_nodes_file, 'r') as f:
        function_nodes = json.load(f)
    with open(rtl_nodes_file, 'r') as f:
        rtl_nodes = json.load(f)

    # Map module -> list of function names
    module_functions = {}
    for func in function_nodes:
        mod = func['parent_module']
        if mod not in module_functions:
            module_functions[mod] = []
        module_functions[mod].append(func['name'])

    call_edges = []

    # Verilog keywords to ignore in call detection
    KEYWORDS = {
        'if', 'else', 'case', 'default', 'begin', 'end', 'always', 'assign', 
        'module', 'endmodule', 'initial', 'forever', 'repeat', 'while', 'for',
        'posedge', 'negedge', 'or', 'and', 'nand', 'nor', 'xor', 'xnor', 'not'
    }

    # Logic chunks (always blocks and assigns)
    for node in rtl_nodes:
        if node['type'] not in ['RTL_LogicChunk', 'RTL_Function']:
            continue
            
        source_id = node.get('id') or node.get('_key')
        module_id = source_id.split('.')[0]
        
        # Get code
        if node['type'] == 'RTL_LogicChunk':
            code = node.get('metadata', {}).get('code', '')
        else:
            code = node.get('full_body', '')
            
        if not code:
            continue
            
        funcs = module_functions.get(module_id, [])
        for func_name in funcs:
            # Look for function call: func_name(
            if re.search(r'\b' + re.escape(func_name) + r'\s*\(', code):
                func_id = sanitize_id(f"{module_id}.{func_name}")
                
                call_edges.append({
                    '_key': get_edge_key(source_id, func_id, 'CALLS'),
                    'from': source_id,
                    'to': func_id,
                    'type': 'CALLS'
                })

    print(f"Detected {len(call_edges)} Function Calls")
    
    # Save output
    with open(os.path.join(data_dir, 'call_edges.json'), 'w') as f:
        json.dump(call_edges, f, indent=2)

    print(f"Output written to:")
    print(f"  - data/call_edges.json")
    print("="*60)

if __name__ == "__main__":
    from config import DATA_DIR
    analyze_calls(DATA_DIR)
