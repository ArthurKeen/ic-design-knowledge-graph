#!/usr/bin/env python3
"""
RTL Generate Block and Loop Extraction

Identifies 'generate' blocks and 'for' loops used for structural 
parameterization and design scalability.
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

def extract_generate_blocks(rtl_dir: str, data_dir: str):
    print("="*60)
    print("Generate Block Extraction Starting...")
    print("="*60)

    # Load modules to map to files
    rtl_nodes_file = os.path.join(data_dir, 'rtl_nodes.json')
    if not os.path.exists(rtl_nodes_file):
        print("rtl_nodes.json not found.")
        return

    with open(rtl_nodes_file, 'r') as f:
        rtl_nodes = json.load(f)

    modules = [n for n in rtl_nodes if n['type'] == 'RTL_Module']
    
    generate_nodes = []
    generate_edges = []

    # Regex for generate blocks
    GENERATE_PATTERN = re.compile(r'generate\b(.*?)\bendgenerate\b', re.DOTALL | re.MULTILINE)
    FOR_PATTERN = re.compile(r'for\s*\((.*?);(.*?);(.*?)\)\s*(?:begin:?\s*(\w+))?', re.DOTALL | re.MULTILINE)

    # Read all Verilog files
    file_map = {}
    for fname in os.listdir(rtl_dir):
        if fname.endswith('.v'):
            path = os.path.join(rtl_dir, fname)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                file_map[fname] = f.read()

    for module in modules:
        module_id = module['id']
        source_file = module.get('metadata', {}).get('file')
        
        if not source_file or source_file not in file_map:
            continue
            
        content = file_map[source_file]
        
        # Extract module body
        mod_match = re.search(rf'\bmodule\s+{re.escape(module_id)}\b(.*?)\bendmodule\b', content, re.DOTALL | re.MULTILINE)
        if not mod_match:
            continue
            
        module_body = mod_match.group(1)
        
        # Find generate blocks
        gen_matches = GENERATE_PATTERN.finditer(module_body)
        for i, g_match in enumerate(gen_matches):
            gen_body = g_match.group(1)
            gen_id = sanitize_id(f"{module_id}.gen_{i}")
            
            # Look for loops inside generate
            loops = []
            for j, f_match in enumerate(FOR_PATTERN.finditer(gen_body)):
                loop_name = f_match.group(4) or f"loop_{j}"
                loops.append({
                    'name': loop_name,
                    'init': f_match.group(1).strip(),
                    'cond': f_match.group(2).strip(),
                    'inc': f_match.group(3).strip()
                })
            
            generate_nodes.append({
                '_key': gen_id,
                'type': 'GenerateBlock',
                'name': f"Generate Block {i}",
                'parent_module': module_id,
                'loop_count': len(loops),
                'loops': loops,
                'metadata': {
                    'has_for_loop': len(loops) > 0,
                    'code_preview': gen_body[:200].strip()
                }
            })
            
            # Link Module to GenerateBlock
            generate_edges.append({
                '_key': get_edge_key(module_id, gen_id, 'CONTAINS_GENERATE'),
                'from': module_id,
                'to': gen_id,
                'type': 'CONTAINS'
            })

    print(f"Extracted {len(generate_nodes)} Generate Blocks")
    
    # Save output
    with open(os.path.join(data_dir, 'generate_nodes.json'), 'w') as f:
        json.dump(generate_nodes, f, indent=2)
    with open(os.path.join(data_dir, 'generate_edges.json'), 'w') as f:
        json.dump(generate_edges, f, indent=2)

    print(f"Output written to:")
    print(f"  - data/generate_nodes.json")
    print(f"  - data/generate_edges.json")
    print("="*60)

if __name__ == "__main__":
    from config import RTL_DIR, DATA_DIR
    extract_generate_blocks(RTL_DIR, DATA_DIR)
