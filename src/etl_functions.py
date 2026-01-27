#!/usr/bin/env python3
"""
RTL Function Extraction from Verilog

This module detects and extracts Verilog functions:
- Function declarations
- Function signatures (return type, inputs)
- Function bodies (code)
- Function usage/calls
- Links to parent modules

Functions are reusable logic blocks that help understand:
- Architectural patterns (register access, instruction decode)
- Code reuse and modularity
- Complex expressions broken into readable chunks
"""

import os
import re
import json
import hashlib
from typing import List, Dict, Tuple, Optional
from utils import NodeResolver, sanitize_id, get_edge_key, VerilogParser


class FunctionExtractor:
    """Extract functions from Verilog modules"""
    
    # Pattern for function declarations
    # Example: function [31:0] get_gpr; ... endfunction
    FUNCTION_PATTERN = re.compile(
        r'^\s*function\s+(?:\[([^\]]+)\]\s+)?(\w+)\s*;(.*?)endfunction',
        re.MULTILINE | re.DOTALL
    )
    
    # Pattern for function inputs within body
    INPUT_PATTERN = re.compile(
        r'^\s*input\s+(?:\[([^\]]+)\]\s+)?(\w+)\s*;',
        re.MULTILINE
    )
    
    def __init__(self, module_name: str, module_body: str, module_key: str, resolver: NodeResolver = None):
        self.module_name = module_name
        self.module_body = module_body
        self.module_key = module_key
        self.resolver = resolver
        self.functions = []
        self.edges = []
    
    def extract(self) -> Tuple[List[Dict], List[Dict]]:
        """Extract functions and their relationships
        
        Returns: (function_nodes, edges)
        """
        for match in self.FUNCTION_PATTERN.finditer(self.module_body):
            return_type = match.group(1)  # e.g., "31:0" or None
            func_name = match.group(2)
            func_body = match.group(3).strip()
            
            # Calculate return width
            return_width = self._calculate_width(return_type) if return_type else 1
            
            # Extract inputs from function body
            inputs = []
            for input_match in self.INPUT_PATTERN.finditer(func_body):
                input_width_expr = input_match.group(1)
                input_name = input_match.group(2)
                input_width = self._calculate_width(input_width_expr) if input_width_expr else 1
                
                inputs.append({
                    'name': input_name,
                    'width': input_width,
                    'width_expr': input_width_expr or '0'
                })
            
            # Extract function calls (simple heuristic: look for function_name(...))
            calls = self._find_function_calls(func_body)
            
            # Count lines of code
            lines_of_code = len([line for line in func_body.split('\n') if line.strip() and not line.strip().startswith('//')])
            
            func_id = sanitize_id(f"{self.module_name}.{func_name}")
            
            func_doc = {
                '_key': func_id,
                'type': 'RTL_Function',
                'name': func_name,
                'parent_module': self.module_key,
                'return_width': return_width,
                'return_type': return_type or 'reg',
                'input_count': len(inputs),
                'inputs': inputs,
                'body': func_body[:500],  # First 500 chars for preview
                'full_body': func_body,  # Full body for analysis
                'metadata': {
                    'lines_of_code': lines_of_code,
                    'calls_other_functions': calls,
                    'complexity': self._calculate_complexity(func_body)
                }
            }
            
            self.functions.append(func_doc)
            
            # Create HAS_FUNCTION edge
            self.edges.append({
                '_key': get_edge_key(self.module_key, func_id, 'HAS_FUNCTION'),
                'from': self.module_key,
                'to': func_id,
                'type': 'HAS_FUNCTION'
            })
            
            # Create FUNCTION_INPUT edges
            if self.resolver:
                for inp in inputs:
                    inp_name = inp['name']
                    # Note: These are internal to the function, but they might be 
                    # derived from or connected to module-level signals in the call.
                    # For now, we link the function to the conceptual input signal 
                    # name if it exists in the module.
                    sig_id = self.resolver.resolve_id(self.module_name, inp_name)
                    self.edges.append({
                        '_key': get_edge_key(func_id, sig_id, 'FUNCTION_INPUT'),
                        'from': func_id,
                        'to': sig_id,
                        'type': 'FUNCTION_INPUT'
                    })
                    
                # Create FUNCTION_OUTPUT edge (linking return value to conceptual signal)
                out_id = self.resolver.resolve_id(self.module_name, func_name)
                self.edges.append({
                    '_key': get_edge_key(func_id, out_id, 'FUNCTION_OUTPUT'),
                    'from': func_id,
                    'to': out_id,
                    'type': 'FUNCTION_OUTPUT'
                })
        
        return self.functions, self.edges
    
    def _calculate_width(self, width_expr: str) -> int:
        """Calculate bit width from expression like '31:0' or '7:0'"""
        try:
            if ':' in width_expr:
                parts = width_expr.split(':')
                high = int(parts[0].strip())
                low = int(parts[1].strip())
                return abs(high - low) + 1
            return int(width_expr)
        except:
            return 1
    
    def _find_function_calls(self, body: str) -> List[str]:
        """Find function calls within the body"""
        # Look for patterns like: function_name(...)
        call_pattern = re.compile(r'\b(\w+)\s*\(')
        calls = []
        
        for match in call_pattern.finditer(body):
            func_name = match.group(1)
            # Filter out known Verilog keywords
            keywords = {'if', 'case', 'for', 'while', 'repeat', 'forever'}
            if func_name not in keywords:
                calls.append(func_name)
        
        return list(set(calls))  # Unique calls
    
    def _calculate_complexity(self, body: str) -> str:
        """Simple complexity heuristic based on control flow"""
        if_count = len(re.findall(r'\bif\b', body))
        case_count = len(re.findall(r'\bcase\b', body))
        for_count = len(re.findall(r'\bfor\b', body))
        
        total_control = if_count + case_count + for_count
        
        if total_control == 0:
            return "Simple"
        elif total_control <= 2:
            return "Moderate"
        else:
            return "Complex"


def extract_functions(rtl_nodes_file: str, rtl_dir: str, data_dir: str = None) -> Tuple[List, List]:
    """Extract functions from all modules
    
    Args:
        rtl_nodes_file: Path to RTL nodes JSON
        rtl_dir: Directory containing Verilog files
        data_dir: Directory for NodeResolver to load nodes from
    
    Returns:
        (function_nodes, function_edges)
    """
    print("="*60)
    print("Function Extraction Starting...")
    print("="*60)
    
    resolver = NodeResolver(data_dir) if data_dir else None
    
    # Load existing RTL nodes
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
    
    all_functions = []
    all_edges = []
    
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
                # Extract Functions
                func_extractor = FunctionExtractor(module_name, body, module_name, resolver=resolver)
                funcs, edges = func_extractor.extract()
                
                if funcs:
                    print(f"\n  [{module_name}]")
                    print(f"    Functions: {len(funcs)}")
                    for func in funcs:
                        complexity = func['metadata']['complexity']
                        inputs = func['input_count']
                        width = func['return_width']
                        print(f"      - {func['name']}: [{width}] ({inputs} inputs, {complexity})")
                    
                    all_functions.extend(funcs)
                    all_edges.extend(edges)
                
                break
    
    print(f"\n{'='*60}")
    print(f"Extraction Complete")
    print(f"  Functions: {len(all_functions)}")
    print(f"  Edges: {len(all_edges)}")
    
    # Summary statistics
    if all_functions:
        avg_inputs = sum(f['input_count'] for f in all_functions) / len(all_functions)
        complex_funcs = len([f for f in all_functions if f['metadata']['complexity'] == 'Complex'])
        print(f"  Avg inputs per function: {avg_inputs:.1f}")
        print(f"  Complex functions: {complex_funcs}")
    
    print(f"{'='*60}\n")
    
    return all_functions, all_edges


if __name__ == "__main__":
    from config import RTL_NODES_FILE, RTL_DIR, DATA_DIR
    
    funcs, edges = extract_functions(RTL_NODES_FILE, RTL_DIR, DATA_DIR)
    
    # Write output files
    with open(os.path.join(DATA_DIR, 'function_nodes.json'), 'w') as f:
        json.dump(funcs, f, indent=2)
    
    with open(os.path.join(DATA_DIR, 'function_edges.json'), 'w') as f:
        json.dump(edges, f, indent=2)
    
    print(f"Output written to:")
    print(f"  - data/function_nodes.json")
    print(f"  - data/function_edges.json")

