#!/usr/bin/env python3
"""
RTL Continuous Assign Extraction from Verilog

Extracts assign statements and builds dataflow graph showing:
- What signals are driven by each assign
- What signals are read by each assign (dependencies)
- Complete signal derivation chains

This enables:
- Dataflow visualization
- Dependency analysis
- Impact analysis (what depends on signal X?)
- Critical path identification
"""

import os
import re
import json
from typing import List, Dict, Tuple, Set
from utils import NodeResolver, sanitize_id, get_edge_key, VerilogParser


class AssignExtractor:
    """Extract continuous assign statements from Verilog"""
    
    # Pattern for assign statements
    # Example: assign out = in1 & in2;
    ASSIGN_PATTERN = re.compile(
        r'^\s*assign\s+([^\s=]+)\s*=\s*([^;]+);',
        re.MULTILINE
    )
    
    def __init__(self, module_name: str, module_body: str, module_key: str, resolver: NodeResolver = None):
        self.module_name = module_name
        self.module_body = module_body
        self.module_key = module_key
        self.resolver = resolver
        self.assigns = []
        self.edges = []
        self.assign_counter = 0
    
    def extract(self) -> Tuple[List[Dict], List[Dict]]:
        """Extract assigns and dataflow relationships
        
        Returns: (assign_nodes, edges)
        """
        for match in self.ASSIGN_PATTERN.finditer(self.module_body):
            lhs = match.group(1).strip()  # Left-hand side (target)
            rhs = match.group(2).strip()  # Right-hand side (expression)
            
            # Clean up LHS (remove bit selects, array indices for now)
            target_signal = self._extract_signal_name(lhs)
            
            # Extract all signals referenced in RHS
            dependencies = self._extract_signal_references(rhs)
            
            # Create assign node
            self.assign_counter += 1
            assign_id = sanitize_id(f"{self.module_name}.assign_{self.assign_counter}")
            
            # Calculate complexity based on expression
            complexity = self._calculate_complexity(rhs)
            
            assign_doc = {
                '_key': assign_id,
                'type': 'RTL_Assign',
                'target': target_signal,
                'expression': rhs[:200],  # Truncate long expressions
                'full_expression': rhs,
                'parent_module': self.module_key,
                'dependency_count': len(dependencies),
                'metadata': {
                    'lhs_full': lhs,  # Full LHS including bit selects
                    'has_bit_select': '[' in lhs,
                    'complexity': complexity,
                    'expression_length': len(rhs)
                }
            }
            
            self.assigns.append(assign_doc)
            
            # Create HAS_ASSIGN edge
            self.edges.append({
                '_key': get_edge_key(self.module_key, assign_id, 'HAS_ASSIGN'),
                'from': self.module_key,
                'to': assign_id,
                'type': 'HAS_ASSIGN'
            })
            
            # Create DRIVES edge (Assign → Target Signal)
            if self.resolver:
                target_signal_id = self.resolver.resolve_id(self.module_name, target_signal)
            else:
                target_signal_id = sanitize_id(f"{self.module_name}.{target_signal}")
                
            self.edges.append({
                '_key': get_edge_key(assign_id, target_signal_id, 'DRIVES'),
                'from': assign_id,
                'to': target_signal_id,
                'type': 'DRIVES',
                'signal_name': target_signal
            })
            
            # Create READS_FROM edges (Assign → Dependency Signals)
            for dep_signal in dependencies:
                if self.resolver:
                    dep_signal_id = self.resolver.resolve_id(self.module_name, dep_signal)
                else:
                    dep_signal_id = sanitize_id(f"{self.module_name}.{dep_signal}")
                    
                edge_key = get_edge_key(assign_id, dep_signal_id, 'READS_FROM')
                
                # Avoid duplicates
                if not any(e.get('_key') == edge_key for e in self.edges):
                    self.edges.append({
                        '_key': edge_key,
                        'from': assign_id,
                        'to': dep_signal_id,
                        'type': 'READS_FROM',
                        'signal_name': dep_signal
                    })
        
        return self.assigns, self.edges
    
    def _extract_signal_name(self, expr: str) -> str:
        """Extract base signal name from expression like 'sig[7:0]' -> 'sig'"""
        # Remove array/bit indices
        base = re.sub(r'\[.*?\]', '', expr)
        return base.strip()
    
    def _extract_signal_references(self, expr: str) -> Set[str]:
        """Extract all signal names referenced in expression"""
        # Remove comments first
        expr = re.sub(r'//.*', '', expr)
        expr = re.sub(r'/\*.*?\*/', '', expr, flags=re.DOTALL)
        
        # Remove string literals, numbers, operators
        # First remove: numbers (including Verilog format like 32'hDEAD)
        expr_clean = re.sub(r"\d+'[bodh][0-9a-fA-F_]+", '', expr)
        expr_clean = re.sub(r'\b\d+\b', '', expr_clean)
        
        # Extract identifiers
        # Matches: signal_name, signal[index], signal[high:low]
        signals = set()
        for match in re.finditer(r'\b([a-zA-Z_]\w*)', expr_clean):
            identifier = match.group(1)
            
            # Filter out Verilog keywords
            keywords = {
                'assign', 'and', 'or', 'not', 'xor', 'nor', 'nand', 'xnor',
                'if', 'else', 'case', 'default', 'begin', 'end',
                'signed', 'unsigned'
            }
            
            if identifier not in keywords:
                signals.add(identifier)
        
        return signals
    
    def _calculate_complexity(self, expr: str) -> str:
        """Calculate expression complexity"""
        # Count operators
        operators = len(re.findall(r'[&|^~+\-*/<>=!]', expr))
        parens = expr.count('(')
        ternary = expr.count('?')
        
        total_complexity = operators + parens * 2 + ternary * 3
        
        if total_complexity <= 3:
            return "Simple"
        elif total_complexity <= 10:
            return "Moderate"
        else:
            return "Complex"


def extract_assigns(rtl_nodes_file: str, rtl_dir: str, data_dir: str = None, limit: int = None) -> Tuple[List, List]:
    """Extract assigns from all modules
    
    Args:
        rtl_nodes_file: Path to RTL nodes JSON
        rtl_dir: Directory containing Verilog files
        data_dir: Directory for NodeResolver to load nodes from
        limit: Optional limit on number of assigns to extract (for testing)
    
    Returns:
        (assign_nodes, assign_edges)
    """
    print("="*60)
    print("Continuous Assign Extraction Starting...")
    print("="*60)
    
    resolver = NodeResolver(data_dir) if data_dir else None
    
    # Load existing RTL nodes
    with open(rtl_nodes_file, 'r') as f:
        rtl_nodes = json.load(f)
    
    modules = [n for n in rtl_nodes if n['type'] == 'RTL_Module']
    print(f"\nFound {len(modules)} modules to analyze")
    if limit:
        print(f"⚠️  Limiting to first {limit} assigns for testing")
    
    # Read Verilog files
    file_map = {}
    for fname in os.listdir(rtl_dir):
        if fname.endswith('.v'):
            path = os.path.join(rtl_dir, fname)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                file_map[fname] = f.read()
    
    all_assigns = []
    all_edges = []
    total_count = 0
    
    # Extract module bodies using VerilogParser
    for module in modules:
        if limit and total_count >= limit:
            break
            
        module_name = module.get('_key') or module.get('id')
        source_file = module.get('metadata', {}).get('file')
        
        if not source_file or source_file not in file_map:
            continue
        
        content = file_map[source_file]
        
        # Find this module's body
        for name, body in VerilogParser.get_module_bodies(content):
            if name == module_name:
                # Extract Assigns
                extractor = AssignExtractor(module_name, body, module_name, resolver=resolver)
                assigns, edges = extractor.extract()
                
                if assigns:
                    print(f"\n  [{module_name}]")
                    print(f"    Assigns: {len(assigns)}")
                    
                    # Show sample
                    if len(assigns) <= 3:
                        for a in assigns:
                            deps = a['dependency_count']
                            print(f"      {a['target']} = ... ({deps} deps, {a['metadata']['complexity']})")
                    else:
                        complex_count = len([a for a in assigns if a['metadata']['complexity'] == 'Complex'])
                        print(f"      Complex: {complex_count}, Simple: {len(assigns) - complex_count}")
                    
                    all_assigns.extend(assigns)
                    all_edges.extend(edges)
                    total_count += len(assigns)
                    
                    if limit and total_count >= limit:
                        break
                
                break
    
    print(f"\n{'='*60}")
    print(f"Extraction Complete")
    print(f"  Assigns: {len(all_assigns)}")
    print(f"  Edges: {len(all_edges)}")
    
    if all_assigns:
        avg_deps = sum(a['dependency_count'] for a in all_assigns) / len(all_assigns)
        complex_count = len([a for a in all_assigns if a['metadata']['complexity'] == 'Complex'])
        print(f"  Avg dependencies: {avg_deps:.1f}")
        print(f"  Complex assigns: {complex_count}")
    
    print(f"{'='*60}\n")
    
    return all_assigns, all_edges


if __name__ == "__main__":
    from config import RTL_NODES_FILE, RTL_DIR, DATA_DIR
    import sys
    
    # Check for limit argument
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    
    assigns, edges = extract_assigns(RTL_NODES_FILE, RTL_DIR, data_dir=DATA_DIR, limit=limit)
    
    # Write output files
    with open(os.path.join(DATA_DIR, 'assign_nodes.json'), 'w') as f:
        json.dump(assigns, f, indent=2)
    
    with open(os.path.join(DATA_DIR, 'assign_edges.json'), 'w') as f:
        json.dump(edges, f, indent=2)
    
    print(f"Output written to:")
    print(f"  - data/assign_nodes.json")
    print(f"  - data/assign_edges.json")
    
    if limit:
        print(f"\n💡 To extract all assigns, run without limit:")
        print(f"   python src/etl_assigns.py")

