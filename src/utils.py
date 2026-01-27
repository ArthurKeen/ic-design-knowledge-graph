import re
import hashlib

def sanitize_id(raw_id):
    """Sanitize ID for ArangoDB _key requirements"""
    if not raw_id:
        return ""
    # Remove Verilog keywords that might be in the raw string
    clean = re.sub(r'\b(reg|wire|input|output|assign)\b', '', raw_id)
    # Remove whitespace and tabs
    clean = re.sub(r'[\s\t\n\r]+', '', clean)
    # Replace other illegal chars with underscore
    clean = re.sub(r'[^a-zA-Z0-9_\-:\.]', '_', clean)
    return clean.strip('_')

def get_edge_key(from_id, to_id, edge_type):
    """Generate deterministic key for edges"""
    raw = f"{from_id}:{to_id}:{edge_type}"
    return hashlib.md5(raw.encode()).hexdigest()

def normalize_hardware_name(name):
    """
    Normalizes Verilog module, port, or signal names for better matching.
    - Lowercases the string.
    - Removes 'or1200_' prefix.
    - Splits by '.' and takes the last part (for module.signal).
    - Replaces underscores with spaces.
    """
    if not name:
        return ""
    
    s = name.lower()
    if s.startswith("or1200_"):
        s = s[7:]
    
    # Handle module.subcomponent or signal.bit
    if "." in s:
        s = s.split(".")[-1]
        
    return s.replace("_", " ").strip()

def strip_comments(text):
    """Remove /* ... */ and // ... comments from a string"""
    # Remove multi-line comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Remove single-line comments
    text = re.sub(r'//.*', '', text)
    return text

def expand_acronym(name, acronym_dict):
    """Expand acronyms in a name using the dictionary by tokenizing.
    
    Example: "if_insn" -> "Instruction Fetch Instruction"
    """
    if not acronym_dict or not name:
        return None
    
    # Normalize name for tokenization
    # Handle both underscores and camelCase (basic)
    tokens = re.split(r'(_|(?=[A-Z]))', name)
    expanded_tokens = []
    changed = False
    
    for t in tokens:
        if not t or t == '_':
            continue
        
        t_lower = t.lower()
        if t_lower in acronym_dict:
            expanded_tokens.append(acronym_dict[t_lower])
            changed = True
        else:
            expanded_tokens.append(t)
            
    if changed:
        return " ".join(expanded_tokens)
    
    return None

class VerilogParser:
    """Shared utilities for parsing Verilog files"""
    
    # Regex to extract a module and its body
    RE_MODULE = re.compile(r'^\s*module\s+(\w+)\s*.*?\bendmodule\b', 
                          re.MULTILINE | re.DOTALL)

    @staticmethod
    def get_module_bodies(content: str):
        """Yields (module_name, module_body) for all modules in content"""
        for match in VerilogParser.RE_MODULE.finditer(content):
            yield match.group(1), match.group(0)

class NodeResolver:
    """Helper to resolve hardware names to their correct ArangoDB IDs.
    
    Handles the 'sig_' prefix mismatch between Ports and Signals.
    """
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.port_ids = set()
        self.signal_ids = set()
        self.module_ids = set()
        self.memory_ids = set()
        self.parameter_ids = set()
        self.global_parameters = {} # name -> full_id
        self._load_nodes()
        
    def _load_nodes(self):
        import json
        import os
        rtl_nodes_file = os.path.join(self.data_dir, 'rtl_nodes.json')
        if os.path.exists(rtl_nodes_file):
            with open(rtl_nodes_file, 'r') as f:
                nodes = json.load(f)
                for n in nodes:
                    nid = n.get('id') or n.get('_key')
                    if n['type'] == 'RTL_Port':
                        self.port_ids.add(nid)
                    elif n['type'] == 'RTL_Signal':
                        self.signal_ids.add(nid)
                    elif n['type'] == 'RTL_Module':
                        self.module_ids.add(nid)
        
        mem_nodes_file = os.path.join(self.data_dir, 'memory_nodes.json')
        if os.path.exists(mem_nodes_file):
            with open(mem_nodes_file, 'r') as f:
                nodes = json.load(f)
                for n in nodes:
                    nid = n.get('id') or n.get('_key')
                    self.memory_ids.add(nid)

        param_nodes_file = os.path.join(self.data_dir, 'param_nodes.json')
        if os.path.exists(param_nodes_file):
            with open(param_nodes_file, 'r') as f:
                nodes = json.load(f)
                for n in nodes:
                    nid = n.get('id') or n.get('_key')
                    self.parameter_ids.add(nid)
                    # Map name to ID for global lookup
                    name = n.get('name')
                    if name:
                        self.global_parameters[name] = nid

    def resolve_id(self, module_id, name):
        """Returns the correct ID for a given name in a module.
        
        Tries Port first, then Signal (with sig_ prefix), then Module itself, then Parameter.
        Returns the original sanitized name if no match found.
        """
        # Sanitized base name
        clean_name = sanitize_id(name)
        
        # 1. Check if it's a port
        port_id = f"{module_id}.{clean_name}"
        if port_id in self.port_ids:
            return port_id
            
        # 2. Check if it's an internal signal (prefixed with sig_)
        sig_id = f"{module_id}.sig_{clean_name}"
        if sig_id in self.signal_ids:
            return sig_id
            
        # 3. Check if it's a memory array
        mem_id = f"{module_id}.{clean_name}"
        if mem_id in self.memory_ids:
            return mem_id

        # 4. Check if it's a parameter in this module
        param_id = f"{module_id}.{clean_name}"
        if param_id in self.parameter_ids:
            return param_id
            
        # 4. Check if it's a global parameter
        if clean_name in self.global_parameters:
            return self.global_parameters[clean_name]
            
        # 5. Check if it's another module 
        if clean_name in self.module_ids:
            return clean_name
            
        # Default fallback
        return port_id
