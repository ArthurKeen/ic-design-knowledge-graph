#!/usr/bin/env python3
"""
RTL Always Block Extraction from Verilog

Extracts always blocks and analyzes:
- Sequential vs combinational logic
- Clock and reset dependencies
- Sensitivity lists
- Block complexity

This enables:
- Sequential logic analysis
- Clock domain identification
- Reset architecture understanding
- Timing-critical path identification
"""

import os
import re
import json
from typing import List, Dict, Tuple, Set
from utils import NodeResolver, sanitize_id, get_edge_key, VerilogParser


class AlwaysBlockExtractor:
    """Extract always blocks from Verilog"""
    
    def __init__(self, module_name: str, module_body: str, source_file: str, resolver: NodeResolver = None):
        self.module_name = module_name
        self.module_body = module_body
        self.source_file = source_file
        self.resolver = resolver
        self.always_blocks = []
        self.edges = []
        self.always_counter = 0
    
    def extract(self) -> Tuple[List[Dict], List[Dict]]:
        """Extract all always blocks
        
        Returns: (always_nodes, edges)
        """
        # Pattern to match always blocks
        # Matches: always @(...) begin ... end OR always @(...) single_statement;
        pattern = re.compile(
            r'always\s*@\s*\(([^)]+)\)\s*(begin.*?end|[^;]+;)',
            re.DOTALL | re.MULTILINE
        )
        
        for match in pattern.finditer(self.module_body):
            sensitivity_list = match.group(1).strip()
            block_body = match.group(2).strip()
            
            # Get line number
            line_num = self.module_body[:match.start()].count('\n') + 1
            
            # Analyze the always block
            self._process_always_block(sensitivity_list, block_body, line_num)
        
        return self.always_blocks, self.edges
    
    def _process_always_block(self, sensitivity_list: str, block_body: str, line_num: int):
        """Process a single always block"""
        self.always_counter += 1
        always_id = sanitize_id(f"{self.module_name}.always_{self.always_counter}")
        
        # Analyze sensitivity list
        analysis = self._analyze_sensitivity_list(sensitivity_list)
        
        # Determine block type
        if analysis['is_sequential']:
            block_type = 'sequential'
        elif analysis['has_edge']:
            block_type = 'edge_sensitive'
        else:
            block_type = 'combinational'
        
        # Count statements (rough complexity)
        statement_count = block_body.count(';')
        if 'begin' in block_body:
            # Adjust for begin/end blocks
            statement_count = max(1, statement_count - 1)
        
        # Determine complexity
        if statement_count <= 3:
            complexity = 'Simple'
        elif statement_count <= 10:
            complexity = 'Moderate'
        else:
            complexity = 'Complex'
        
        # Create always block node
        always_doc = {
            '_key': always_id,
            'type': 'RTL_Always',
            'block_type': block_type,
            'sensitivity_list': sensitivity_list[:200],
            'parent_module': self.module_name,
            'statement_count': statement_count,
            'complexity': complexity,
            'metadata': {
                'source_file': self.source_file,
                'line_number': line_num,
                'has_reset': analysis['has_reset'],
                'reset_type': analysis['reset_type'],
                'clock_signal': analysis['clock_signal'],
                'reset_signal': analysis['reset_signal'],
                'sensitivity_signals': analysis['sensitivity_signals'],
                'has_begin_end': 'begin' in block_body.lower()
            }
        }
        
        self.always_blocks.append(always_doc)
        
        # Create HAS_ALWAYS edge
        self.edges.append({
            '_key': get_edge_key(self.module_name, always_id, 'HAS_ALWAYS'),
            'from': self.module_name,
            'to': always_id,
            'type': 'HAS_ALWAYS'
        })
        
        # Create CLOCKED_BY edge if there's a clock
        if analysis['clock_signal']:
            if self.resolver:
                clock_id = self.resolver.resolve_id(self.module_name, analysis['clock_signal'])
            else:
                clock_id = sanitize_id(f"{self.module_name}.{analysis['clock_signal']}")
                
            self.edges.append({
                '_key': get_edge_key(always_id, clock_id, 'CLOCKED_BY'),
                'from': always_id,
                'to': clock_id,
                'type': 'CLOCKED_BY',
                'signal_name': analysis['clock_signal'],
                'edge_type': analysis['clock_edge']
            })
        
        # Create RESET_BY edge if there's a reset
        if analysis['reset_signal']:
            if self.resolver:
                reset_id = self.resolver.resolve_id(self.module_name, analysis['reset_signal'])
            else:
                reset_id = sanitize_id(f"{self.module_name}.{analysis['reset_signal']}")
                
            self.edges.append({
                '_key': get_edge_key(always_id, reset_id, 'RESET_BY'),
                'from': always_id,
                'to': reset_id,
                'type': 'RESET_BY',
                'signal_name': analysis['reset_signal'],
                'reset_type': analysis['reset_type']
            })
        
        # Create SENSITIVE_TO edges for other signals
        for sig in analysis['sensitivity_signals']:
            if sig not in [analysis['clock_signal'], analysis['reset_signal']]:
                if self.resolver:
                    sig_id = self.resolver.resolve_id(self.module_name, sig)
                else:
                    sig_id = sanitize_id(f"{self.module_name}.{sig}")
                    
                edge_key = get_edge_key(always_id, sig_id, 'SENSITIVE_TO')
                if not any(e.get('_key') == edge_key for e in self.edges):
                    self.edges.append({
                        '_key': edge_key,
                        'from': always_id,
                        'to': sig_id,
                        'type': 'SENSITIVE_TO',
                        'signal_name': sig
                    })
    
    def _analyze_sensitivity_list(self, sens_list: str) -> Dict:
        """Analyze the sensitivity list to extract clock, reset, and signal info"""
        result = {
            'is_sequential': False,
            'has_edge': False,
            'has_reset': False,
            'clock_signal': None,
            'clock_edge': None,
            'reset_signal': None,
            'reset_type': None,
            'sensitivity_signals': []
        }
        
        # Check for edge-sensitive (posedge/negedge)
        if 'posedge' in sens_list.lower() or 'negedge' in sens_list.lower():
            result['has_edge'] = True
            result['is_sequential'] = True
        
        # Extract clock signal (first posedge/negedge signal is usually clock)
        clock_match = re.search(r'(posedge|negedge)\s+(\w+)', sens_list, re.IGNORECASE)
        if clock_match:
            result['clock_edge'] = clock_match.group(1).lower()
            result['clock_signal'] = clock_match.group(2)
        
        # Extract reset signal (look for rst, reset in sensitivity list)
        # Check for OR1200_RST_EVENT macro or explicit reset
        reset_match = re.search(r'OR1200_RST_EVENT\s+(\w+)', sens_list)
        if reset_match:
            result['has_reset'] = True
            result['reset_signal'] = reset_match.group(1)
            result['reset_type'] = 'async'  # OR1200_RST_EVENT is async
        else:
            # Look for posedge/negedge rst/reset
            reset_match = re.search(r'(posedge|negedge)\s+(rst\w*|reset\w*)', sens_list, re.IGNORECASE)
            if reset_match:
                result['has_reset'] = True
                result['reset_signal'] = reset_match.group(2)
                result['reset_type'] = 'async'  # In sensitivity list = async
        
        # Extract all signal names from sensitivity list
        # Remove posedge/negedge/or keywords
        cleaned = re.sub(r'\b(posedge|negedge|or)\b', '', sens_list, flags=re.IGNORECASE)
        cleaned = re.sub(r'`\w+', '', cleaned)  # Remove macros
        
        # Extract identifiers
        signals = re.findall(r'\b([a-zA-Z_]\w*)\b', cleaned)
        result['sensitivity_signals'] = list(set(signals))  # Deduplicate
        
        return result


def extract_always_blocks(rtl_nodes_file: str, rtl_dir: str, data_dir: str = None) -> Tuple[List, List]:
    """Extract always blocks from all modules
    
    Args:
        rtl_nodes_file: Path to RTL nodes JSON
        rtl_dir: Directory containing Verilog files
        data_dir: Directory for NodeResolver to load nodes from
    
    Returns:
        (always_nodes, always_edges)
    """
    print("="*60)
    print("Always Block Extraction Starting...")
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
    
    all_always = []
    all_edges = []
    
    stats = {
        'sequential': 0,
        'combinational': 0,
        'edge_sensitive': 0,
        'with_reset': 0,
        'with_clock': 0
    }
    
    # Extract module bodies using VerilogParser
    for module in modules:
        module_name = module.get('_key') or module.get('id')
        source_file = module.get('metadata', {}).get('file')
        
        if not source_file or source_file not in file_map:
            continue
        
        content = file_map[source_file]
        
        # Find this module's body using centralized parser
        for name, body in VerilogParser.get_module_bodies(content):
            if name == module_name:
                # Extract always blocks
                extractor = AlwaysBlockExtractor(module_name, body, source_file, resolver=resolver)
                always_blocks, edges = extractor.extract()
                
                if always_blocks:
                    # Update stats
                    for block in always_blocks:
                        stats[block['block_type']] += 1
                        if block['metadata']['has_reset']:
                            stats['with_reset'] += 1
                        if block['metadata']['clock_signal']:
                            stats['with_clock'] += 1
                    
                    print(f"\n  [{module_name}]")
                    print(f"    Always blocks: {len(always_blocks)}")
                    
                    # Show breakdown
                    seq = len([b for b in always_blocks if b['block_type'] == 'sequential'])
                    comb = len([b for b in always_blocks if b['block_type'] == 'combinational'])
                    if seq:
                        print(f"      Sequential: {seq}")
                    if comb:
                        print(f"      Combinational: {comb}")
                    
                    all_always.extend(always_blocks)
                    all_edges.extend(edges)
                
                break
    
    print(f"\n{'='*60}")
    print(f"Extraction Complete")
    print(f"  Total Always Blocks: {len(all_always)}")
    print(f"    Sequential: {stats['sequential']}")
    print(f"    Combinational: {stats['combinational']}")
    print(f"    Edge-sensitive: {stats['edge_sensitive']}")
    print(f"  Clock dependencies: {stats['with_clock']}")
    print(f"  Reset dependencies: {stats['with_reset']}")
    print(f"  Total Edges: {len(all_edges)}")
    
    if all_always:
        avg_statements = sum(b['statement_count'] for b in all_always) / len(all_always)
        complex_count = len([b for b in all_always if b['complexity'] == 'Complex'])
        print(f"  Avg statements: {avg_statements:.1f}")
        print(f"  Complex blocks: {complex_count}")
    
    print(f"{'='*60}\n")
    
    return all_always, all_edges


if __name__ == "__main__":
    from config import RTL_NODES_FILE, RTL_DIR, DATA_DIR
    
    always_blocks, edges = extract_always_blocks(RTL_NODES_FILE, RTL_DIR, data_dir=DATA_DIR)
    
    # Write output files
    with open(os.path.join(DATA_DIR, 'always_nodes.json'), 'w') as f:
        json.dump(always_blocks, f, indent=2)
    
    with open(os.path.join(DATA_DIR, 'always_edges.json'), 'w') as f:
        json.dump(edges, f, indent=2)
    
    print(f"Output written to:")
    print(f"  - data/always_nodes.json")
    print(f"  - data/always_edges.json")

