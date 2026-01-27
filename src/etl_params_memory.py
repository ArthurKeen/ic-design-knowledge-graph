#!/usr/bin/env python3
"""
RTL Parameter and Memory Extraction from Verilog

This module detects and extracts:
- Parameters (parameter/localparam) - configuration constants
- Memory structures (RAM/ROM, register files, memory arrays)

Detection Strategy:
1. Find parameter/localparam declarations
2. Track parameter usage in signal widths, array sizes
3. Find memory declarations (large reg arrays)
4. Extract memory dimensions and types
5. Link to modules, signals, and ports
"""

import os
import re
import json
import hashlib
from typing import List, Dict, Tuple, Optional
from utils import sanitize_id, get_edge_key, VerilogParser


class ParameterExtractor:
    """Extract parameters and localparams from Verilog modules"""
    
    PARAMETER_PATTERN = re.compile(
        r'^\s*parameter\s+(?:\[([^\]]+)\]\s*)?(\w+)\s*=\s*([^;]+);',
        re.MULTILINE
    )
    
    LOCALPARAM_PATTERN = re.compile(
        r'^\s*localparam\s+(?:\[([^\]]+)\]\s*)?(\w+)\s*=\s*([^;]+);',
        re.MULTILINE
    )
    
    DEFINE_PATTERN = re.compile(
        r'^\s*`define\s+(\w+)\s+([^\n]+)',
        re.MULTILINE
    )
    
    def __init__(self, module_name: str, module_body: str, module_key: str, file_content: str = None):
        self.module_name = module_name
        self.module_body = module_body
        self.module_key = module_key
        self.file_content = file_content or module_body
        self.parameters = []
        self.edges = []
    
    def extract(self) -> Tuple[List[Dict], List[Dict]]:
        """Extract parameters and their relationships
        
        Returns: (parameter_nodes, edges)
        """
        param_dict = {}
        
        # Extract parameters
        for match in self.PARAMETER_PATTERN.finditer(self.module_body):
            width = match.group(1)  # e.g., "7:0" or None
            name = match.group(2)
            value = match.group(3).strip()
            
            param_id = sanitize_id(f"{self.module_name}.{name}")
            param_dict[name] = param_id
            
            param_doc = {
                '_key': param_id,
                'type': 'RTL_Parameter',
                'name': name,
                'value': value,
                'parent_module': self.module_key,
                'metadata': {
                    'kind': 'parameter',
                    'width': width,
                    'scope': 'module'
                }
            }
            
            # Try to evaluate if it's a simple expression
            if self._is_numeric(value):
                param_doc['evaluated_value'] = self._evaluate_value(value)
            
            self.parameters.append(param_doc)
            
            # Create HAS_PARAMETER edge
            self.edges.append({
                '_key': get_edge_key(self.module_key, param_id, 'HAS_PARAMETER'),
                'from': self.module_key,
                'to': param_id,
                'type': 'HAS_PARAMETER'
            })
        
        # Extract localparams
        for match in self.LOCALPARAM_PATTERN.finditer(self.module_body):
            width = match.group(1)
            name = match.group(2)
            value = match.group(3).strip()
            
            param_id = sanitize_id(f"{self.module_name}.{name}")
            param_dict[name] = param_id
            
            param_doc = {
                '_key': param_id,
                'type': 'RTL_Parameter',
                'name': name,
                'value': value,
                'parent_module': self.module_key,
                'metadata': {
                    'kind': 'localparam',
                    'width': width,
                    'scope': 'module'
                }
            }
            
            if self._is_numeric(value):
                param_doc['evaluated_value'] = self._evaluate_value(value)
            
            self.parameters.append(param_doc)
            
            # Create HAS_PARAMETER edge
            self.edges.append({
                '_key': get_edge_key(self.module_key, param_id, 'HAS_PARAMETER'),
                'from': self.module_key,
                'to': param_id,
                'type': 'HAS_PARAMETER'
            })
        
        # Extract `define macros (file-level)
        for match in self.DEFINE_PATTERN.finditer(self.file_content):
            name = match.group(1)
            value = match.group(2).strip()
            
            # Extract all defines
            param_id = sanitize_id(f"{self.module_name}.{name}")
            param_dict[name] = param_id
            
            is_module_specific = self.module_name.upper() in name.upper()
            
            param_doc = {
                '_key': param_id,
                'type': 'RTL_Parameter',
                'name': name,
                'value': value,
                'parent_module': self.module_key,
                'metadata': {
                    'kind': 'define',
                    'width': None,
                    'scope': 'module' if is_module_specific else 'file',
                    'is_global': not is_module_specific
                }
            }
            
            if self._is_numeric(value):
                param_doc['evaluated_value'] = self._evaluate_value(value)
            
            self.parameters.append(param_doc)
            
            # Create HAS_PARAMETER edge
            self.edges.append({
                '_key': get_edge_key(self.module_key, param_id, 'HAS_PARAMETER'),
                'from': self.module_key,
                'to': param_id,
                'type': 'HAS_PARAMETER'
            })
        
        return self.parameters, self.edges
    
    def _is_numeric(self, value: str) -> bool:
        """Check if value is a simple numeric expression"""
        # Handle Verilog number formats: 8'd255, 4'b1010, 32'hFFFF
        if re.match(r"^\d+'[bodh][0-9a-fA-F_]+$", value):
            return True
        # Handle simple decimals
        if re.match(r"^\d+$", value):
            return True
        return False
    
    def _evaluate_value(self, value: str) -> Optional[int]:
        """Try to evaluate a numeric value"""
        try:
            # Verilog format: 8'd255
            if "'" in value:
                match = re.match(r"^(\d+)'([bodh])([0-9a-fA-F_]+)$", value)
                if match:
                    width = int(match.group(1))
                    base = match.group(2)
                    num_str = match.group(3).replace('_', '')
                    
                    base_map = {'b': 2, 'o': 8, 'd': 10, 'h': 16}
                    return int(num_str, base_map[base])
            
            # Simple decimal
            return int(value)
        except:
            return None


class MemoryExtractor:
    """Extract memory structures (RAM/ROM, register files) from Verilog"""
    
    # Pattern for memory declarations: reg [width] name [depth];
    MEMORY_PATTERN = re.compile(
        r'^\s*reg\s+\[([^\]]+)\]\s+(\w+)\s*\[([^\]]+)\]\s*;',
        re.MULTILINE
    )
    
    def __init__(self, module_name: str, module_body: str, module_key: str):
        self.module_name = module_name
        self.module_body = module_body
        self.module_key = module_key
        self.memories = []
        self.edges = []
    
    def extract(self) -> Tuple[List[Dict], List[Dict]]:
        """Extract memory structures
        
        Returns: (memory_nodes, edges)
        """
        for match in self.MEMORY_PATTERN.finditer(self.module_body):
            width_expr = match.group(1).strip()  # e.g., "31:0"
            name = match.group(2)
            depth_expr = match.group(3).strip()  # e.g., "255:0" or "0:255"
            
            # Calculate dimensions
            width = self._calculate_width(width_expr)
            depth = self._calculate_depth(depth_expr)
            
            # Only treat as memory if depth > threshold (e.g., 16)
            if depth < 16:
                continue  # Skip small arrays, they're just signals
            
            mem_id = sanitize_id(f"{self.module_name}.{name}")
            
            # Determine memory type based on naming conventions
            mem_type = self._infer_memory_type(name)
            
            mem_doc = {
                '_key': mem_id,
                'type': 'RTL_Memory',
                'name': name,
                'parent_module': self.module_key,
                'width': width,
                'depth': depth,
                'total_bits': width * depth,
                'metadata': {
                    'width_expr': width_expr,
                    'depth_expr': depth_expr,
                    'memory_type': mem_type,
                    'estimated_kb': (width * depth) / (8 * 1024)
                }
            }
            
            self.memories.append(mem_doc)
            
            # Create HAS_MEMORY edge
            self.edges.append({
                '_key': get_edge_key(self.module_key, mem_id, 'HAS_MEMORY'),
                'from': self.module_key,
                'to': mem_id,
                'type': 'HAS_MEMORY'
            })

            # STORED_IN: Detect signals that represent the memory's storage
            # In Verilog, the 'reg [...] name [...]' is both the declaration and the storage
            # But we often want to link the memory node to the signal name
            self.edges.append({
                '_key': get_edge_key(mem_id, mem_id, 'STORED_IN'),
                'from': mem_id,
                'to': mem_id, # Self-link for now to satisfy schema, or find backing signal
                'type': 'STORED_IN'
            })
        
        return self.memories, self.edges
    
    def _calculate_width(self, width_expr: str) -> int:
        """Calculate bit width from expression like '31:0' or '7:0'"""
        try:
            parts = width_expr.split(':')
            if len(parts) == 2:
                high = int(parts[0].strip())
                low = int(parts[1].strip())
                return abs(high - low) + 1
            return int(width_expr)
        except:
            return 1
    
    def _calculate_depth(self, depth_expr: str) -> int:
        """Calculate depth from expression like '255:0' or '0:255'"""
        try:
            parts = depth_expr.split(':')
            if len(parts) == 2:
                high = int(parts[0].strip())
                low = int(parts[1].strip())
                return abs(high - low) + 1
            return int(depth_expr)
        except:
            return 0
    
    def _infer_memory_type(self, name: str) -> str:
        """Infer memory type from naming conventions"""
        name_lower = name.lower()
        
        if 'ram' in name_lower:
            if 'spram' in name_lower or 'single' in name_lower:
                return 'Single-Port RAM'
            elif 'dpram' in name_lower or 'dual' in name_lower:
                return 'Dual-Port RAM'
            else:
                return 'RAM'
        elif 'rom' in name_lower:
            return 'ROM'
        elif 'rf' in name_lower or 'regfile' in name_lower:
            return 'Register File'
        elif 'fifo' in name_lower:
            return 'FIFO'
        elif 'cache' in name_lower:
            return 'Cache'
        elif 'tlb' in name_lower:
            return 'TLB (Translation Lookaside Buffer)'
        elif 'mem' in name_lower:
            return 'Memory Array'
        else:
            return 'Memory Array'


def extract_parameters_and_memory(rtl_nodes_file: str, rtl_dir: str) -> Tuple[List, List, List, List]:
    """Extract parameters and memory from all modules
    
    Args:
        rtl_nodes_file: Path to RTL nodes JSON
        rtl_dir: Directory containing Verilog files
    
    Returns:
        (param_nodes, mem_nodes, param_edges, mem_edges)
    """
    print("="*60)
    print("Parameter & Memory Extraction Starting...")
    print("="*60)
    
    all_params = []
    all_memories = []
    all_param_edges = []
    all_mem_edges = []

    # 1. Extract Global Defines from or1200_defines.v
    defines_file = os.path.join(rtl_dir, 'or1200_defines.v')
    if os.path.exists(defines_file):
        print(f"Extracting global defines from {defines_file}...")
        with open(defines_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # Use same pattern as ParameterExtractor
            for match in ParameterExtractor.DEFINE_PATTERN.finditer(content):
                name = match.group(1)
                value = match.group(2).strip()
                
                # Check for comment at end of line
                value = re.sub(r'//.*', '', value).strip()
                
                param_id = sanitize_id(f"GLOBAL.{name}")
                param_doc = {
                    '_key': param_id,
                    'type': 'RTL_Parameter',
                    'name': name,
                    'value': value,
                    'parent_module': 'GLOBAL',
                    'metadata': {
                        'kind': 'define',
                        'scope': 'global',
                        'is_global': True
                    }
                }
                all_params.append(param_doc)
        print(f"  Found {len(all_params)} global defines")

    # 2. Load existing RTL nodes
    with open(rtl_nodes_file, 'r') as f:
        rtl_nodes = json.load(f)
    
    modules = [n for n in rtl_nodes if n['type'] == 'RTL_Module']
    print(f"\nFound {len(modules)} modules to analyze")
    
    # Read Verilog files
    file_map = {}
    for fname in os.listdir(rtl_dir):
        if fname.endswith('.v'):
            path = os.path.join(rtl_dir, fname)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                file_map[fname] = f.read()
    
    all_params = []
    all_memories = []
    all_param_edges = []
    all_mem_edges = []
    
    # Extract module bodies using VerilogParser
    for module in modules:
        module_name = module.get('_key') or module.get('id')
        source_file = module.get('metadata', {}).get('file')
        
        if not source_file or source_file not in file_map:
            continue
        
        content = file_map[source_file]
        
        # Find this module's body
        for name, body in VerilogParser.get_module_bodies(content):
            if name == module_name:
                # Extract Parameters
                param_extractor = ParameterExtractor(module_name, body, module_name, content)
                params, param_edges = param_extractor.extract()
                
                # Extract Memory
                mem_extractor = MemoryExtractor(module_name, body, module_name)
                mems, mem_edges = mem_extractor.extract()
                
                if params or mems:
                    print(f"\n  [{module_name}]")
                    if params:
                        print(f"    Parameters: {len(params)}")
                        # Link signals/ports to these parameters
                        module_nodes = [n for n in rtl_nodes if n['id'].startswith(module_name + '.') and n['type'] in ('RTL_Port', 'RTL_Signal', 'RTL_Memory')]
                        for p in params:
                            p_name = p['name']
                            for node in module_nodes:
                                # Check if parameter name is in width_expr or depth_expr
                                meta = node.get('metadata', {})
                                w_expr = meta.get('width_expr', '')
                                d_expr = meta.get('depth_expr', '')
                                
                                if p_name in str(w_expr) or p_name in str(d_expr):
                                    node_id = node.get('id') or node.get('_key')
                                    param_id = p['_key']
                                    all_param_edges.append({
                                        '_key': get_edge_key(node_id, param_id, 'USES_PARAMETER'),
                                        'from': node_id,
                                        'to': param_id,
                                        'type': 'USES_PARAMETER'
                                    })
                    if mems:
                        print(f"    Memories: {len(mems)}")
                        for mem in mems:
                            size_kb = mem['metadata']['estimated_kb']
                            print(f"      - {mem['name']}: {mem['width']}x{mem['depth']} ({size_kb:.1f} KB)")
                    
                    all_params.extend(params)
                    all_memories.extend(mems)
                    all_param_edges.extend(param_edges)
                    all_mem_edges.extend(mem_edges)
                
                break
    
    print(f"\n{'='*60}")
    print(f"Extraction Complete")
    print(f"  Parameters: {len(all_params)}")
    print(f"  Memories: {len(all_memories)}")
    print(f"  Total Edges: {len(all_param_edges) + len(all_mem_edges)}")
    print(f"{'='*60}\n")
    
    return all_params, all_memories, all_param_edges, all_mem_edges


if __name__ == "__main__":
    from config import RTL_NODES_FILE, RTL_DIR, DATA_DIR
    
    params, mems, param_edges, mem_edges = extract_parameters_and_memory(
        RTL_NODES_FILE,
        RTL_DIR
    )
    
    # Write output files
    with open(os.path.join(DATA_DIR, 'param_nodes.json'), 'w') as f:
        json.dump(params, f, indent=2)
    
    with open(os.path.join(DATA_DIR, 'memory_nodes.json'), 'w') as f:
        json.dump(mems, f, indent=2)
    
    all_edges = param_edges + mem_edges
    with open(os.path.join(DATA_DIR, 'param_memory_edges.json'), 'w') as f:
        json.dump(all_edges, f, indent=2)
    
    print(f"Output written to:")
    print(f"  - data/param_nodes.json")
    print(f"  - data/memory_nodes.json")
    print(f"  - data/param_memory_edges.json")

