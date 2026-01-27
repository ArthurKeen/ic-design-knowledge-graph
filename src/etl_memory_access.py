#!/usr/bin/env python3
"""
RTL Memory Access and Port Analysis

Identifies how logic chunks (always blocks, assigns) access memory arrays
and extracts dedicated MemoryPort nodes.
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

def analyze_memory_access(data_dir: str):
    print("="*60)
    print("Memory Access Analysis Starting...")
    print("="*60)

    resolver = NodeResolver(data_dir)

    memory_nodes_file = os.path.join(data_dir, 'memory_nodes.json')
    rtl_nodes_file = os.path.join(data_dir, 'rtl_nodes.json')

    if not os.path.exists(memory_nodes_file) or not os.path.exists(rtl_nodes_file):
        print("Required data files not found.")
        return

    with open(memory_nodes_file, 'r') as f:
        memory_nodes = json.load(f)
    with open(rtl_nodes_file, 'r') as f:
        rtl_nodes = json.load(f)

    # Map module -> list of memory names
    module_memories = {}
    for mem in memory_nodes:
        mod = mem['parent_module']
        if mod not in module_memories:
            module_memories[mod] = []
        module_memories[mod].append(mem['name'])

    access_edges = []
    port_nodes = []
    port_edges = []

    # Logic chunks (always blocks and assigns)
    for node in rtl_nodes:
        if node['type'] != 'RTL_LogicChunk':
            continue
            
        logic_id = node['id']
        module_id = logic_id.split('.')[0]
        code = node.get('metadata', {}).get('code', '')
        
        if module_id not in module_memories or not code:
            continue
            
        mems = module_memories[module_id]
        for mem_name in mems:
            # Look for memory access: mem_name[index]
            # Write access: mem_name[index] <= ... or mem_name[index] = ...
            write_pattern = re.compile(rf'\b{re.escape(mem_name)}\s*\[(.*?)\]\s*(?:<=|=)')
            # Read access: ... = ... mem_name[index] ...
            read_pattern = re.compile(rf'=\s*.*?\b{re.escape(mem_name)}\s*\[(.*?)\]')
            
            mem_id = sanitize_id(f"{module_id}.{mem_name}")
            
            # Check for writes
            writes = write_pattern.findall(code)
            for index_expr in writes:
                access_edges.append({
                    '_key': get_edge_key(logic_id, mem_id, f"ACCESSES_WRITE_{index_expr}"),
                    'from': logic_id,
                    'to': mem_id,
                    'type': 'ACCESSES',
                    'metadata': {
                        'access_type': 'write',
                        'index_expression': index_expr.strip()
                    }
                })
                
            # Check for reads
            reads = read_pattern.findall(code)
            for index_expr in reads:
                # Avoid matching if it was already caught as a write (some complex expressions might)
                access_edges.append({
                    '_key': get_edge_key(logic_id, mem_id, f"ACCESSES_READ_{index_expr}"),
                    'from': logic_id,
                    'to': mem_id,
                    'type': 'ACCESSES',
                    'metadata': {
                        'access_type': 'read',
                        'index_expression': index_expr.strip()
                    }
                })

    # Link Ports to MemoryPort
    for mod_id, mems in module_memories.items():
        # Get all ports and signals for this module to use in PART_OF_PORT
        module_nodes = [n for n in rtl_nodes if n['id'].startswith(mod_id + '.') and n['type'] in ('RTL_Port', 'RTL_Signal')]
        
        for mem_name in mems:
            # Look for ports/signals like mem_name_addr, mem_name_data, etc.
            suffixes = ['addr', 'dat_i', 'dat_o', 'di', 'doq', 'we', 'en', 'ce', 'sel', 'ack', 'cyc', 'stb']
            matched_node_ids = []
            
            for node in module_nodes:
                name = node['label'].lower()
                if any(name.endswith(f"_{s}") or name == s for s in suffixes):
                    matched_node_ids.append(node['id'])
            
            if len(matched_node_ids) >= 2:
                port_node_id = sanitize_id(f"{mod_id}.{mem_name}_port")
                
                # Check if we already created this MemoryPort node
                if not any(n['_key'] == port_node_id for n in port_nodes):
                    port_nodes.append({
                        '_key': port_node_id,
                        'type': 'MemoryPort',
                        'name': f"{mem_name} Port",
                        'parent_module': mod_id,
                        'metadata': {
                            'memory': mem_name
                        }
                    })
                    
                    # Link Memory to MemoryPort
                    mem_id = sanitize_id(f"{mod_id}.{mem_name}")
                    port_edges.append({
                        '_key': get_edge_key(mem_id, port_node_id, 'HAS_PORT'),
                        'from': mem_id,
                        'to': port_node_id,
                        'type': 'MEMORY_PORT'
                    })
                
                # Link Ports/Signals to MemoryPort
                for node_id in matched_node_ids:
                    port_edges.append({
                        '_key': get_edge_key(node_id, port_node_id, 'PART_OF_PORT'),
                        'from': node_id,
                        'to': port_node_id,
                        'type': 'PART_OF_BUS'
                    })

    print(f"Detected {len(access_edges)} Memory Accesses")
    print(f"Identified {len(port_nodes)} Memory Ports")
    
    # Save output
    with open(os.path.join(data_dir, 'memory_access_edges.json'), 'w') as f:
        json.dump(access_edges, f, indent=2)
    with open(os.path.join(data_dir, 'memory_port_nodes.json'), 'w') as f:
        json.dump(port_nodes, f, indent=2)
    with open(os.path.join(data_dir, 'memory_port_edges.json'), 'w') as f:
        json.dump(port_edges, f, indent=2)

    print(f"Output written to:")
    print(f"  - data/memory_access_edges.json")
    print(f"  - data/memory_port_nodes.json")
    print(f"  - data/memory_port_edges.json")
    print("="*60)

if __name__ == "__main__":
    from config import DATA_DIR
    analyze_memory_access(DATA_DIR)
