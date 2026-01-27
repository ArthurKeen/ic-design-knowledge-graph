#!/usr/bin/env python3
"""
RTL Bus Interface Extraction

Identifies bus interfaces (e.g., AXI, Wishbone) by grouping related ports
based on common naming conventions (prefixes like iwb_, dwb_, axi_).
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

# Common bus prefixes and their full names
BUS_PREFIXES = {
    'iwb_': 'Wishbone Instruction',
    'dwb_': 'Wishbone Data',
    'wb_': 'Wishbone',
    'axi_': 'AXI',
    'apb_': 'APB',
    'ahb_': 'AHB',
    'avm_': 'Avalon-MM',
    'avs_': 'Avalon-ST',
    'lsu_': 'Load/Store Unit',
    'spr_': 'Special Purpose Register'
}

def extract_bus_interfaces(data_dir: str):
    print("="*60)
    print("Bus Interface Extraction Starting...")
    print("="*60)

    rtl_nodes_file = os.path.join(data_dir, 'rtl_nodes.json')
    if not os.path.exists(rtl_nodes_file):
        print(f"Error: {rtl_nodes_file} not found")
        return

    with open(rtl_nodes_file, 'r') as f:
        rtl_nodes = json.load(f)

    # Group ports by module and prefix
    # module_id -> { prefix -> [port_ids] }
    module_bus_groups = {}
    port_to_module = {}

    for node in rtl_nodes:
        if node['type'] == 'RTL_Port':
            port_id = node['id']
            port_label = node['label']
            
            # Extract module name from port ID (e.g., "or1200_top.iwb_clk_i")
            # The format is module_name.port_name
            parts = port_id.split('.')
            if len(parts) < 2:
                continue
            
            module_id = parts[0]
            port_name = parts[1]
            
            # Check if port name starts with any known prefix
            found_prefix = None
            for prefix in BUS_PREFIXES.keys():
                if port_name.startswith(prefix):
                    found_prefix = prefix
                    break
            
            if found_prefix:
                if module_id not in module_bus_groups:
                    module_bus_groups[module_id] = {}
                if found_prefix not in module_bus_groups[module_id]:
                    module_bus_groups[module_id][found_prefix] = []
                module_bus_groups[module_id][found_prefix].append(port_id)
                port_to_module[port_id] = module_id

    bus_nodes = []
    bus_edges = []

    for module_id, prefixes in module_bus_groups.items():
        for prefix, ports in prefixes.items():
            # Only treat as a bus if it has 3 or more ports
            if len(ports) < 3:
                continue
                
            bus_type_name = BUS_PREFIXES[prefix]
            interface_name = f"{prefix.strip('_').upper()} Interface"
            bus_id = sanitize_id(f"{module_id}.bus_{prefix.strip('_')}")
            
            bus_node = {
                '_key': bus_id,
                'type': 'BusInterface',
                'name': interface_name,
                'interface_type': bus_type_name,
                'parent_module': module_id,
                'port_count': len(ports),
                'metadata': {
                    'prefix': prefix,
                    'module': module_id
                }
            }
            bus_nodes.append(bus_node)
            
            # Link Module to BusInterface (IMPLEMENTS)
            bus_edges.append({
                '_key': get_edge_key(module_id, bus_id, 'IMPLEMENTS'),
                'from': module_id,
                'to': bus_id,
                'type': 'IMPLEMENTS'
            })
            
            # Link Ports to BusInterface (PART_OF_BUS)
            for port_id in ports:
                bus_edges.append({
                    '_key': get_edge_key(port_id, bus_id, 'PART_OF_BUS'),
                    'from': port_id,
                    'to': bus_id,
                    'type': 'PART_OF_BUS'
                })

    print(f"Extracted {len(bus_nodes)} Bus Interfaces")
    print(f"Created {len(bus_edges)} relationships")
    
    # Save output
    with open(os.path.join(data_dir, 'bus_nodes.json'), 'w') as f:
        json.dump(bus_nodes, f, indent=2)
        
    with open(os.path.join(data_dir, 'bus_edges.json'), 'w') as f:
        json.dump(bus_edges, f, indent=2)

    print(f"Output written to:")
    print(f"  - data/bus_nodes.json")
    print(f"  - data/bus_edges.json")
    print("="*60)

if __name__ == "__main__":
    from config import DATA_DIR
    extract_bus_interfaces(DATA_DIR)
