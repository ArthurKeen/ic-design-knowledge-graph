#!/usr/bin/env python3
"""
Clock Domain and CDC (Clock Domain Crossing) Analysis

This module:
1. Identifies dedicated ClockDomain nodes.
2. Maps modules and signals to ClockDomains based on CLOCKED_BY relationships.
3. Detects signals that CROSS_DOMAIN (driven in one domain, read in another).
4. Creates dedicated ClockDomain nodes and relationships.
"""

import os
import re
import json
import hashlib
from typing import List, Dict, Tuple, Set, Optional
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

def extract_signals_from_code(code: str) -> Tuple[Set[str], Set[str]]:
    """Extract LHS (driven) and RHS (read) signals from Verilog code"""
    # Remove comments
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    lhs_signals = set()
    rhs_signals = set()
    
    # Match non-blocking and blocking assignments
    # Handles: sig <= expr; sig = expr; sig[7:0] <= expr;
    assign_pattern = re.compile(r'(\b\w+\b)(?:\s*\[[^\]]*\])?\s*(?:<=|=)\s*([^;]+);')
    
    for match in assign_pattern.finditer(code):
        lhs = match.group(1)
        rhs = match.group(2)
        
        lhs_signals.add(lhs)
        
        # Extract RHS identifiers
        rhs_ids = re.findall(r'\b([a-zA-Z_]\w*)\b', rhs)
        for rid in rhs_ids:
            # Filter Verilog keywords
            if rid.lower() not in {
                'begin', 'end', 'if', 'else', 'case', 'default', 'posedge', 
                'negedge', 'or', 'assign', 'always', 'reg', 'wire', 'input', 
                'output', 'module', 'endmodule'
            }:
                # Also filter numbers if they were caught (though regex avoids most)
                if not rid.isdigit():
                    rhs_signals.add(rid)
                    
    return lhs_signals, rhs_signals

def analyze_clocks_and_cdc(data_dir: str):
    print("="*60)
    print("Clock Domain & CDC Analysis Starting...")
    print("="*60)

    resolver = NodeResolver(data_dir)

    # Paths
    always_nodes_file = os.path.join(data_dir, 'always_nodes.json')
    always_edges_file = os.path.join(data_dir, 'always_edges.json')
    rtl_nodes_file = os.path.join(data_dir, 'rtl_nodes.json')

    # Load data
    with open(always_nodes_file, 'r') as f:
        always_nodes = json.load(f)
    with open(always_edges_file, 'r') as f:
        always_edges = json.load(f)
    with open(rtl_nodes_file, 'r') as f:
        rtl_nodes = json.load(f)

    # Map always block ID -> clock signal
    always_to_clock = {}
    for edge in always_edges:
        if edge['type'] == 'CLOCKED_BY':
            always_to_clock[edge['from']] = {
                'clock_id': edge['to'],
                'clock_name': edge.get('signal_name', 'unknown'),
                'edge': edge.get('edge_type', 'posedge')
            }

    # Map logic chunk ID -> code
    logic_code = {}
    for node in rtl_nodes:
        if node['type'] == 'RTL_LogicChunk':
            logic_code[node['id']] = node.get('metadata', {}).get('code', '')

    # Clock Domain Nodes
    clock_domains = {} # clock_name -> domain_id
    clock_domain_nodes = []
    
    # Signal Domain Mapping: signal_id -> set of clock_ids that drive it
    signal_drivers = {} 
    # Signal Domain Mapping: signal_id -> set of clock_ids that read it
    signal_readers = {}

    cdc_edges = []
    domain_edges = []

    # Process each always block
    for always in always_nodes:
        always_id = always['_key']
        module_name = always['parent_module']
        
        if always_id not in always_to_clock:
            continue
            
        clock_info = always_to_clock[always_id]
        clock_name = clock_info['clock_name']
        clock_id = clock_info['clock_id']
        
        # Ensure ClockDomain node exists
        domain_key = sanitize_id(f"domain_{clock_name}")
        if domain_key not in clock_domains:
            clock_domains[domain_key] = clock_name
            clock_domain_nodes.append({
                '_key': domain_key,
                'type': 'ClockDomain',
                'name': clock_name,
                'clock_signal': clock_id,
                'metadata': {
                    'edge': clock_info['edge']
                }
            })
            
            # Link Module to ClockDomain
            domain_edges.append({
                '_key': get_edge_key(module_name, domain_key, 'CLOCKED_BY'),
                'from': module_name,
                'to': domain_key,
                'type': 'CLOCKED_BY'
            })

        # Analyze code for this always block
        code = logic_code.get(always_id, '')
        if not code:
            continue
            
        lhs_sigs, rhs_sigs = extract_signals_from_code(code)
        
        # Track which clock drives which signal
        for sig in lhs_sigs:
            sig_id = resolver.resolve_id(module_name, sig)
            if sig_id not in signal_drivers:
                signal_drivers[sig_id] = set()
            signal_drivers[sig_id].add(clock_id)
            
            # Link Signal to ClockDomain
            domain_edges.append({
                '_key': get_edge_key(sig_id, domain_key, 'CLOCKED_BY'),
                'from': sig_id,
                'to': domain_key,
                'type': 'CLOCKED_BY'
            })

        # Track which clock reads which signal
        for sig in rhs_sigs:
            sig_id = resolver.resolve_id(module_name, sig)
            if sig_id not in signal_readers:
                signal_readers[sig_id] = set()
            signal_readers[sig_id].add(clock_id)

    # Detect CDC: Signal driven by Clock A, but read by Clock B (A != B)
    cdc_count = 0
    for sig_id, readers in signal_readers.items():
        drivers = signal_drivers.get(sig_id, set())
        
        for reader_clk in readers:
            for driver_clk in drivers:
                if reader_clk != driver_clk:
                    # Clock Domain Crossing detected!
                    edge_key = get_edge_key(sig_id, reader_clk, 'CROSSES_DOMAIN')
                    
                    # Avoid duplicates
                    if not any(e['_key'] == edge_key for e in cdc_edges):
                        cdc_edges.append({
                            '_key': edge_key,
                            'from': sig_id,
                            'to': reader_clk,
                            'type': 'CROSSES_DOMAIN',
                            'metadata': {
                                'source_domain_clk': driver_clk,
                                'target_domain_clk': reader_clk,
                                'signal_id': sig_id
                            }
                        })
                        cdc_count += 1

    print(f"Found {len(clock_domain_nodes)} Clock Domains")
    print(f"Detected {cdc_count} Potential CDC Violations")
    
    # Save output
    with open(os.path.join(data_dir, 'clock_nodes.json'), 'w') as f:
        json.dump(clock_domain_nodes, f, indent=2)
        
    with open(os.path.join(data_dir, 'clock_edges.json'), 'w') as f:
        json.dump(domain_edges + cdc_edges, f, indent=2)

    print(f"Output written to:")
    print(f"  - data/clock_nodes.json")
    print(f"  - data/clock_edges.json")
    print("="*60)

if __name__ == "__main__":
    from config import DATA_DIR
    analyze_clocks_and_cdc(DATA_DIR)
