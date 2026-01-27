#!/usr/bin/env python3
"""
RTL Assertion/Constraint Extraction from Verilog

Extracts verification infrastructure and design constraints:
- Runtime checks ($display warnings/errors)
- Design constraints from comments (MUST, SHALL, etc.)
- Simulation-only blocks (translate_off regions)
- Debug instrumentation (ifdef VERBOSE/DEBUG)

This captures design intent and verification requirements.
"""

import os
import re
import json
import hashlib
from typing import List, Dict, Tuple
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


class AssertionExtractor:
    """Extract assertions and design constraints from Verilog"""
    
    def __init__(self, module_name: str, full_file_content: str, source_file: str, resolver: NodeResolver = None):
        self.module_name = module_name
        self.content = full_file_content
        self.source_file = source_file
        self.resolver = resolver
        self.assertions = []
        self.edges = []
        self.assertion_counter = 0
    
    def extract(self) -> Tuple[List[Dict], List[Dict]]:
        """Extract all assertions/constraints
        
        Returns: (assertion_nodes, edges)
        """
        # Extract different types of constraints
        self._extract_display_checks()
        self._extract_constraint_comments()
        self._extract_synthesis_pragmas()
        self._extract_ifdef_blocks()
        
        return self.assertions, self.edges
    
    def _extract_display_checks(self):
        """Extract $display WARNING/ERROR/FATAL statements"""
        # Pattern for $display with WARNING, ERROR, or FATAL
        pattern = re.compile(
            r'\$display\s*\(\s*"([^"]*(?:WARNING|ERROR|FATAL)[^"]*)"[^)]*\)',
            re.IGNORECASE
        )
        
        for match in pattern.finditer(self.content):
            message = match.group(1)
            line_num = self.content[:match.start()].count('\n') + 1
            
            # Determine severity
            msg_upper = message.upper()
            if 'FATAL' in msg_upper:
                severity = 'FATAL'
            elif 'ERROR' in msg_upper:
                severity = 'ERROR'
            else:
                severity = 'WARNING'
            
            self._add_assertion(
                kind='runtime_check',
                severity=severity,
                description=message[:200],
                full_text=message,
                line_number=line_num,
                context='simulation'
            )
    
    def _extract_constraint_comments(self):
        """Extract comments with MUST, SHALL, etc."""
        # Pattern for constraint comments
        patterns = [
            (r'//.*\b([Mm][Uu][Ss][Tt].*)', 'requirement'),
            (r'//.*\b([Ss][Hh][Aa][Ll][Ll].*)', 'requirement'),
            (r'//.*\b([Nn][Oo][Tt][Ee]:.*)', 'note'),
            (r'//.*\b([Ww][Aa][Rr][Nn][Ii][Nn][Gg]:.*)', 'warning'),
        ]
        
        for pattern_str, kind in patterns:
            pattern = re.compile(pattern_str)
            for match in pattern.finditer(self.content):
                constraint_text = match.group(1).strip()
                line_num = self.content[:match.start()].count('\n') + 1
                
                # Determine severity from context
                text_upper = constraint_text.upper()
                if 'CRITICAL' in text_upper or 'FATAL' in text_upper:
                    severity = 'HIGH'
                elif 'WARNING' in text_upper:
                    severity = 'MEDIUM'
                else:
                    severity = 'LOW'
                
                self._add_assertion(
                    kind='design_constraint',
                    severity=severity,
                    description=constraint_text[:200],
                    full_text=constraint_text,
                    line_number=line_num,
                    context='comment'
                )
    
    def _extract_synthesis_pragmas(self):
        """Extract simulation-only code blocks (translate_off/on)"""
        # Find translate_off ... translate_on regions
        pattern = re.compile(
            r'//\s*synopsys\s+translate_off\s*(.*?)\s*//\s*synopsys\s+translate_on',
            re.DOTALL | re.IGNORECASE
        )
        
        for match in pattern.finditer(self.content):
            block_content = match.group(1).strip()
            line_num = self.content[:match.start()].count('\n') + 1
            
            # Summarize what's in the block
            lines = [l.strip() for l in block_content.split('\n') if l.strip() and not l.strip().startswith('//')]
            if lines:
                summary = lines[0][:100] if lines[0] else "simulation-only code"
                
                self._add_assertion(
                    kind='simulation_only',
                    severity='INFO',
                    description=f"Simulation-only block: {summary}",
                    full_text=block_content[:500],  # Limit size
                    line_number=line_num,
                    context='synthesis_pragma'
                )
    
    def _extract_ifdef_blocks(self):
        """Extract ifdef DEBUG/VERBOSE blocks"""
        pattern = re.compile(
            r'`ifdef\s+(OR1200_VERBOSE|OR1200_DEBUG|DEBUG|VERBOSE)\s*(.*?)\s*`endif',
            re.DOTALL
        )
        
        for match in pattern.finditer(self.content):
            ifdef_name = match.group(1)
            block_content = match.group(2).strip()
            line_num = self.content[:match.start()].count('\n') + 1
            
            # Summarize
            lines = [l.strip() for l in block_content.split('\n') if l.strip() and not l.strip().startswith('//')]
            if lines:
                summary = lines[0][:100] if lines[0] else "debug instrumentation"
                
                self._add_assertion(
                    kind='debug_instrumentation',
                    severity='INFO',
                    description=f"{ifdef_name}: {summary}",
                    full_text=block_content[:500],
                    line_number=line_num,
                    context=f'ifdef_{ifdef_name}'
                )
    
    def _add_assertion(self, kind, severity, description, full_text, line_number, context):
        """Helper to add an assertion node"""
        self.assertion_counter += 1
        assertion_id = sanitize_id(f"{self.module_name}.assertion_{self.assertion_counter}")
        
        assertion_doc = {
            '_key': assertion_id,
            'type': 'RTL_Assertion',
            'kind': kind,  # runtime_check, design_constraint, simulation_only, debug_instrumentation
            'severity': severity,  # FATAL, ERROR, WARNING, HIGH, MEDIUM, LOW, INFO
            'description': description,
            'full_text': full_text,
            'parent_module': self.module_name,
            'metadata': {
                'source_file': self.source_file,
                'line_number': line_number,
                'context': context
            }
        }
        
        self.assertions.append(assertion_doc)
        
        # Create HAS_ASSERTION edge
        self.edges.append({
            '_key': get_edge_key(self.module_name, assertion_id, 'HAS_ASSERTION'),
            'from': self.module_name,
            'to': assertion_id,
            'type': 'HAS_ASSERTION'
        })

        # Create CHECKS_SIGNAL edges if we can identify signals in the description
        if self.resolver:
            # Simple heuristic: Look for words that match known signals/ports in the module
            words = re.findall(r'\b\w+\b', full_text)
            for word in set(words):
                sig_id = self.resolver.resolve_id(self.module_name, word)
                # verify_id check: if the resolver found a matching Port or Signal node
                if sig_id in self.resolver.port_ids or sig_id in self.resolver.signal_ids:
                    self.edges.append({
                        '_key': get_edge_key(assertion_id, sig_id, 'CHECKS_SIGNAL'),
                        'from': assertion_id,
                        'to': sig_id,
                        'type': 'CHECKS_SIGNAL'
                    })


def extract_assertions(rtl_dir: str, data_dir: str = None) -> Tuple[List, List]:
    """Extract assertions from all Verilog files
    
    Args:
        rtl_dir: Directory containing Verilog files
        data_dir: Directory for NodeResolver to load nodes from
    
    Returns:
        (assertion_nodes, assertion_edges)
    """
    print("="*60)
    print("Assertion/Constraint Extraction Starting...")
    print("="*60)
    
    resolver = NodeResolver(data_dir) if data_dir else None
    
    # Read all Verilog files
    file_map = {}
    for fname in os.listdir(rtl_dir):
        if fname.endswith('.v'):
            path = os.path.join(rtl_dir, fname)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                file_map[fname] = f.read()
    
    print(f"\nAnalyzing {len(file_map)} Verilog files...")
    
    all_assertions = []
    all_edges = []
    
    # Extract module names and bodies using regex
    RE_MODULE_BODY = re.compile(r'^\s*module\s+(\w+)\s*.*?\bendmodule\b', re.MULTILINE | re.DOTALL)
    
    stats = {
        'runtime_check': 0,
        'design_constraint': 0,
        'simulation_only': 0,
        'debug_instrumentation': 0
    }
    
    for fname, content in file_map.items():
        # Find all modules in this file with their bodies
        for match in RE_MODULE_BODY.finditer(content):
            module_name = match.group(1)
            module_body = match.group(0)
            
            extractor = AssertionExtractor(module_name, module_body, fname, resolver=resolver)
            assertions, edges = extractor.extract()
            
            if assertions:
                print(f"\n  [{module_name}]")
                for a in assertions:
                    kind = a['kind']
                    stats[kind] += 1
                    severity = a['severity']
                    desc = a['description'][:60]
                    print(f"    [{severity:7}] {kind:25} {desc}")
                
                all_assertions.extend(assertions)
                all_edges.extend(edges)
    
    print(f"\n{'='*60}")
    print(f"Extraction Complete")
    print(f"  Total Assertions: {len(all_assertions)}")
    print(f"    Runtime Checks: {stats['runtime_check']}")
    print(f"    Design Constraints: {stats['design_constraint']}")
    print(f"    Simulation-only Blocks: {stats['simulation_only']}")
    print(f"    Debug Instrumentation: {stats['debug_instrumentation']}")
    print(f"  Total Edges: {len(all_edges)}")
    print(f"{'='*60}\n")
    
    return all_assertions, all_edges


if __name__ == "__main__":
    from config import RTL_DIR, DATA_DIR
    
    assertions, edges = extract_assertions(RTL_DIR, DATA_DIR)
    
    # Write output files
    with open(os.path.join(DATA_DIR, 'assertion_nodes.json'), 'w') as f:
        json.dump(assertions, f, indent=2)
    
    with open(os.path.join(DATA_DIR, 'assertion_edges.json'), 'w') as f:
        json.dump(edges, f, indent=2)
    
    print(f"Output written to:")
    print(f"  - data/assertion_nodes.json")
    print(f"  - data/assertion_edges.json")

