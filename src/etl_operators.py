#!/usr/bin/env python3
"""
RTL Operator and Arithmetic Extraction

Detects arithmetic and logical operators (+, *, <<, etc.) within logic chunks
and creates dedicated Operator nodes and USES_OPERATOR relationships.
"""

import os
import re
import json
import hashlib
from typing import List, Dict, Tuple, Set
from utils import NodeResolver

def get_edge_key(from_id, to_id, edge_type):
    """Generate deterministic key for edges"""
    raw = f"{from_id}:{to_id}:{edge_type}"
    return hashlib.md5(raw.encode()).hexdigest()

def sanitize_id(raw_id):
    """Sanitize ID for ArangoDB _key requirements"""
    clean = re.sub(r'[\s\t\n\r]+', '', raw_id)
    clean = re.sub(r'[^a-zA-Z0-9_\-:\.]', '_', clean)
    return clean.strip('_')

# Operators to detect
OPERATOR_MAP = {
    r'\+': 'Adder',
    r'\-': 'Subtractor',
    r'\*': 'Multiplier',
    r'\/': 'Divider',
    r'<<<': 'Arithmetic Left Shifter',
    r'>>>': 'Arithmetic Right Shifter',
    r'<<': 'Logical Left Shifter',
    r'>>': 'Logical Right Shifter',
    r'>=': 'Comparator',
    r'<=': 'Comparator', # Will handle context below
    r'>': 'Comparator',
    r'<': 'Comparator',
    r'==': 'Equality',
    r'!=': 'Equality',
}

def analyze_operators(data_dir: str):
    print("="*60)
    print("Operator Extraction Starting...")
    print("="*60)

    resolver = NodeResolver(data_dir)

    rtl_nodes_file = os.path.join(data_dir, 'rtl_nodes.json')
    if not os.path.exists(rtl_nodes_file):
        print("rtl_nodes.json not found.")
        return

    with open(rtl_nodes_file, 'r') as f:
        rtl_nodes = json.load(f)

    operator_nodes = []
    operator_edges = []
    
    # Track created operators to avoid duplicates per module
    # (module_id, op_type) -> operator_id
    module_operators = {}

    for node in rtl_nodes:
        if node['type'] != 'RTL_LogicChunk':
            continue
            
        logic_id = node['id']
        module_id = logic_id.split('.')[0]
        code = node.get('metadata', {}).get('code', '')
        
        if not code:
            continue

        # Simple extraction of target signal(s) from code
        # In assign statements it's easy: assign target = ...
        targets = []
        if 'assign' in code:
            m = re.search(r'assign\s+(\w+)', code)
            if m: targets.append(m.group(1))
        else:
            # In always blocks, look for LHS signals
            # matches: sig <= expr; or sig = expr;
            m_list = re.findall(r'(\w+)\s*(?:\[[^\]]*\])?\s*(?:<=|=)', code)
            targets.extend(m_list)

        # Detect operators
        for pattern, op_type in OPERATOR_MAP.items():
            # For <=, we must ensure it's not the non-blocking assignment
            if pattern == r'<=':
                # Look for <= inside parentheses (e.g., if (a <= b))
                if not re.search(r'\(\s*.*?' + pattern + r'.*?\)', code):
                    continue
            else:
                if not re.search(pattern, code):
                    continue

            # Create or get operator node for this module
            op_key = (module_id, op_type)
            if op_key not in module_operators:
                op_id = sanitize_id(f"{module_id}.op_{op_type.replace(' ', '_')}")
                module_operators[op_key] = op_id
                operator_nodes.append({
                    '_key': op_id,
                    'type': 'Operator',
                    'name': op_type,
                    'operator_type': op_type,
                    'parent_module': module_id
                })
                # Link Module to Operator
                operator_edges.append({
                    '_key': get_edge_key(module_id, op_id, 'HAS_OPERATOR'),
                    'from': module_id,
                    'to': op_id,
                    'type': 'HAS_OPERATOR'
                })

            op_id = module_operators[op_key]
            
            # Link logic chunk to operator
            operator_edges.append({
                '_key': get_edge_key(logic_id, op_id, 'USES_OPERATOR'),
                'from': logic_id,
                'to': op_id,
                'type': 'USES_OPERATOR'
            })
            
            # Link target signals to operator (if known)
            for t_sig in set(targets):
                sig_id = resolver.resolve_id(module_id, t_sig)
                # We don't verify signal existence here for speed, 
                # but USES_OPERATOR (Signal -> Operator) is requested
                operator_edges.append({
                    '_key': get_edge_key(sig_id, op_id, 'USES_OPERATOR'),
                    'from': sig_id,
                    'to': op_id,
                    'type': 'USES_OPERATOR'
                })

    print(f"Extracted {len(operator_nodes)} Operator types across modules")
    print(f"Created {len(operator_edges)} USES_OPERATOR relationships")
    
    # Save output
    with open(os.path.join(data_dir, 'operator_nodes.json'), 'w') as f:
        json.dump(operator_nodes, f, indent=2)
    with open(os.path.join(data_dir, 'operator_edges.json'), 'w') as f:
        json.dump(operator_edges, f, indent=2)

    print(f"Output written to:")
    print(f"  - data/operator_nodes.json")
    print(f"  - data/operator_edges.json")
    print("="*60)

if __name__ == "__main__":
    from config import DATA_DIR
    analyze_operators(DATA_DIR)
