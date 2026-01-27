import os
import re
import json
import random
from config import (
    RTL_DIR, RTL_NODES_FILE, RTL_EDGES_FILE,
    COL_MODULE, COL_PORT, COL_SIGNAL, COL_LOGIC,
    EDGE_HAS_PORT, EDGE_HAS_SIGNAL, EDGE_CONTAINS, EDGE_WIRED_TO, EDGE_DEPENDS_ON,
    EDGE_OVERRIDES
)
from utils import sanitize_id, get_edge_key, VerilogParser, strip_comments, expand_acronym

# Regex patterns
# Improved regex to capture width expression and handle comments better
RE_INPUT = re.compile(r'^\s*input\s+(?:\[([^\]]*)\]\s*)?([^;]+);(?:\s*//(.*))?', re.MULTILINE)
RE_OUTPUT = re.compile(r'^\s*output\s+(?:\[([^\]]*)\]\s*)?([^;]+);(?:\s*//(.*))?', re.MULTILINE)
RE_SIGNALS = re.compile(r'^\s*(wire|reg)\s+(?:\[([^\]]*)\]\s*)?([^;]+);(?:\s*//(.*))?', re.MULTILINE)
RE_ALWAYS = re.compile(r'^\s*always\s*@\s*\(.*?\)\s*(?:begin\b.*?end\b|[^;]*?;)', re.MULTILINE | re.DOTALL)
RE_ASSIGN = re.compile(r'^\s*assign\s+.*?;', re.MULTILINE)

# Load acronym dictionary
ACRONYM_DICT = {}
try:
    with open(os.path.join(os.path.dirname(__file__), 'or1200_acronyms.json')) as f:
        ACRONYM_DICT = json.load(f)
    print(f"Loaded {len(ACRONYM_DICT)} acronym mappings")
except FileNotFoundError:
    print("Warning: or1200_acronyms.json not found, acronym expansion disabled")

def parse_verilog_files():
    print(f"Scanning RTL directory: {RTL_DIR}")
    
    files = [f for f in os.listdir(RTL_DIR) if f.endswith('.v')]
    
    # Pass 1: Collect all module names
    module_names = set()
    file_map = {} # filename -> content
    
    for fname in files:
        path = os.path.join(RTL_DIR, fname)
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            file_map[fname] = content
            # Pass 1: Find all modules in this file
            for module_name, _ in VerilogParser.get_module_bodies(content):
                module_names.add(module_name)
    
    print(f"Found {len(module_names)} modules.")

    nodes = []
    edges = []

    # Pass 2: Extract details and relationships
    for fname, content in file_map.items():
        for current_module, module_body in VerilogParser.get_module_bodies(content):
            # Pre-process module body: strip block comments to avoid confusing regexes
            # e.g. "/*wire*/reg s;" should match as a reg.
            clean_body = re.sub(r'/\*.*?\*/', ' ', module_body, flags=re.DOTALL)
            
            # Extract Header Comments (Looking for a Description block anywhere in the file)
            # Find the "Description" block in the whole file if it exists
            # Enhanced to handle the //// trailing chars in OpenCores headers
            description_match = re.search(r'Description\s*/*\n\s*(?:/{2,4}\s*)(.*?)\n\s*(?:/{2,4}\s*)\n', content, re.DOTALL | re.IGNORECASE)
            summary = ""
            if description_match:
                raw_summary = description_match.group(1)
                # Clean up: remove trailing //// and normalize whitespace
                lines = [l.split('//')[0].strip() for l in raw_summary.split('\n')]
                summary = " ".join(lines).strip()
            
            if not summary:
                # Try a broader search for any multi-line comment containing "Description"
                alt_desc = re.search(r'Description\s*:?\s*(.*?)(?:\n\s*\n|\*/|Author)', content, re.DOTALL | re.IGNORECASE)
                if alt_desc:
                    raw_summary = alt_desc.group(1)
                    # Remove all leading/trailing comment chars from each line
                    lines = [re.sub(r'^[\s/*]+|[\s/*]+$', '', l).strip() for l in raw_summary.split('\n')]
                    summary = " ".join([l for l in lines if l]).strip()

            if not summary:
                # Try to find the first line after the header block that looks like a title
                # e.g. ////  OR1200's ALU                                                ////
                title_match = re.search(r'/{2,4}\s*(OR1200.*?)\s*/{2,4}', content, re.IGNORECASE)
                if title_match:
                    summary = title_match.group(1).strip()
            
            if not summary:
                # Fallback to the existing logic but search further back (50 lines)
                start_idx = match_mod.start()
                pre_module_content = content[:start_idx]
                lines = pre_module_content.splitlines()[-50:] if len(pre_module_content) > 0 else []
                
                comment_lines = []
                for line in reversed(lines):
                    line = line.strip()
                    if not line: continue
                    
                    if line.startswith('//'):
                        msg = line[2:].strip()
                    elif line.startswith('*'):
                        msg = line.replace('*', '').strip()
                    elif line.startswith('/*'): 
                        continue
                    elif line.endswith('*/'):
                        continue
                    else: 
                        break
                        
                    if msg and not any(x in msg.lower() for x in ["copyright", "author", "http", "www.", "rev "]):
                         comment_lines.insert(0, msg)
                summary = " ".join(comment_lines)
            if not summary:
                 # Fallback: Look inside module if header is empty
                 lines = module_body.splitlines()
                 comment_lines = []
                 for line in lines[:10]:
                     line = line.strip()
                     if line.startswith('//'):
                         comment_lines.append(line[2:].strip())
                 summary = " ".join(comment_lines)

            # Create Module Node
            expanded = expand_acronym(current_module, ACRONYM_DICT)
            nodes.append({
                "id": current_module,
                "label": current_module,
                "type": COL_MODULE,
                "metadata": {
                    "file": fname,
                    "code_content": module_body,
                    "summary": summary,
                    "expanded_name": expanded
                }
            })
            
            # 1. Parsing Ports
            seen_ports = set()
            module_lines = clean_body.splitlines()
            
            # Helper to find comment above a line index
            def find_comment_above(lines, line_idx):
                for i in range(line_idx - 1, max(-1, line_idx - 5), -1):
                    line = lines[i].strip()
                    if line.startswith('//'):
                        return line[2:].strip()
                    if line.endswith('*/'):
                        return line.replace('*/', '').replace('/*', '').replace('*', '').strip()
                    if line and not line.startswith('/'):
                        break
                return ""

            # Inputs
            for match in RE_INPUT.finditer(clean_body):
                width_expr = match.group(1).strip() if match.group(1) else ""
                raw_ports_str = match.group(2)
                raw_ports = strip_comments(raw_ports_str)
                comment = match.group(3).strip() if match.group(3) else ""
                
                if not comment:
                    # Find line index in the module body
                    match_pos = match.start()
                    line_idx = clean_body[:match_pos].count('\n')
                    comment = find_comment_above(module_lines, line_idx)
                
                # Split by comma
                for p in raw_ports.split(','):
                    p = p.strip()
                    if not p: continue
                    # Sanitization
                    p_clean = sanitize_id(p)
                    if not p_clean or p_clean in seen_ports: continue
                    seen_ports.add(p_clean)
                    port_id = f"{current_module}.{p_clean}"
                    
                    expanded = expand_acronym(p_clean, ACRONYM_DICT)
                    nodes.append({
                        "id": port_id,
                        "label": p_clean,
                        "type": COL_PORT,
                        "metadata": {
                            "direction": "input", 
                            "description": comment,
                            "expanded_name": expanded,
                            "width_expr": width_expr
                        }
                    })
                    edges.append({
                        "_key": get_edge_key(current_module, port_id, EDGE_HAS_PORT),
                        "from": current_module,
                        "to": port_id,
                        "type": EDGE_HAS_PORT
                    })

            # Outputs
            for match in RE_OUTPUT.finditer(clean_body):
                width_expr = match.group(1).strip() if match.group(1) else ""
                raw_ports_str = match.group(2)
                raw_ports = strip_comments(raw_ports_str)
                comment = match.group(3).strip() if match.group(3) else ""
                
                if not comment:
                    match_pos = match.start()
                    line_idx = clean_body[:match_pos].count('\n')
                    comment = find_comment_above(module_lines, line_idx)
                
                for p in raw_ports.split(','):
                    p = p.strip()
                    if not p: continue
                    p_clean = sanitize_id(p)
                    if not p_clean or p_clean in seen_ports: continue
                    seen_ports.add(p_clean)
                    port_id = f"{current_module}.{p_clean}"
                    
                    expanded = expand_acronym(p_clean, ACRONYM_DICT)
                    nodes.append({
                        "id": port_id,
                        "label": p_clean,
                        "type": COL_PORT,
                        "metadata": {
                            "direction": "output", 
                            "description": comment,
                            "expanded_name": expanded,
                            "width_expr": width_expr
                        }
                    })
                    edges.append({
                        "_key": get_edge_key(current_module, port_id, EDGE_HAS_PORT),
                        "from": current_module,
                        "to": port_id,
                        "type": EDGE_HAS_PORT
                    })

            # Internal Signals (Wires/Regs)
            sig_seen = set()
            for match in RE_SIGNALS.finditer(clean_body):
                sig_type = match.group(1)
                width_expr = match.group(2).strip() if match.group(2) else ""
                raw_signals_str = match.group(3)
                raw_signals = strip_comments(raw_signals_str)
                comment = match.group(4).strip() if match.group(4) else ""
                
                if not comment:
                    match_pos = match.start()
                    line_idx = clean_body[:match_pos].count('\n')
                    comment = find_comment_above(module_lines, line_idx)
                
                # Split by comma (handles multiple signals on one line)
                for s in raw_signals.split(','):
                    s = s.strip()
                    if not s: continue
                    
                    # Extract name if there's an assignment (e.g., "wire s = 1'b0;")
                    if '=' in s:
                        s = s.split('=')[0].strip()
                    
                    # Sanitization
                    s_clean = sanitize_id(s)
                    if not s_clean or s_clean in sig_seen: continue
                    sig_seen.add(s_clean)
                    
                    # Prefix with 'sig_' to avoid collision with Ports (e.g. esr)
                    sig_id = f"{current_module}.sig_{s_clean}"
                    
                    expanded = expand_acronym(s_clean, ACRONYM_DICT)
                    nodes.append({
                        "id": sig_id,
                        "label": s_clean,
                        "type": COL_SIGNAL,
                        "metadata": {
                            "datatype": sig_type,
                            "description": comment,
                            "expanded_name": expanded,
                            "width_expr": width_expr
                        }
                    })
                    edges.append({
                        "_key": get_edge_key(current_module, sig_id, EDGE_HAS_SIGNAL),
                        "from": current_module,
                        "to": sig_id,
                        "type": EDGE_HAS_SIGNAL
                    })
            
            # 2. Parsing Submodules (CONTAINS)
            for other_mod in module_names:
                if other_mod == current_module:
                    continue
                pattern = r'\b' + re.escape(other_mod) + r'\s+(?:#\s*\(.*?\)\s*)?(\w+)\s*\('
                instances = re.findall(pattern, module_body, re.DOTALL | re.MULTILINE)
                for inst_name in instances:
                    edges.append({
                        "_key": get_edge_key(current_module, other_mod, EDGE_CONTAINS),
                        "from": current_module,
                        "to": other_mod,
                        "type": EDGE_CONTAINS,
                        "metadata": {"instance_name": inst_name}
                    })

            # 4. Parsing Logic Chunks (always blocks and assign statements)
            for idx, match in enumerate(RE_ALWAYS.finditer(clean_body)):
                block_code = match.group(0).strip()
                block_id = f"{current_module}.always_{idx}"
                block_label = block_code.split('\\n')[0].strip()
                nodes.append({
                    "id": block_id,
                    "label": block_label,
                    "type": COL_LOGIC,
                    "metadata": {
                        "code": block_code,
                        "chunk_type": "always_block"
                    }
                })
                edges.append({
                    "_key": get_edge_key(current_module, block_id, EDGE_CONTAINS),
                    "from": current_module,
                    "to": block_id,
                    "type": EDGE_CONTAINS
                })

            for idx, match in enumerate(RE_ASSIGN.finditer(clean_body)):
                assign_code = match.group(0).strip()
                assign_id = f"{current_module}.assign_{idx}"
                nodes.append({
                    "id": assign_id,
                    "label": f"assign {idx}",
                    "type": COL_LOGIC,
                    "metadata": {
                        "code": assign_code,
                        "chunk_type": "assign_statement"
                    }
                })
                edges.append({
                    "_key": get_edge_key(current_module, assign_id, EDGE_CONTAINS),
                    "from": current_module,
                    "to": assign_id,
                    "type": EDGE_CONTAINS
                })

    # Pass 3: Extract Module Dependencies (DEPENDS_ON)
    print("Extracting module dependencies...")
    dependencies_count = 0
    
    for fname, content in file_map.items():
        for parent_module, module_body in VerilogParser.get_module_bodies(content):
            clean_body = re.sub(r'/\*.*?\*/', ' ', module_body, flags=re.DOTALL)
            
            # Look for instantiations: other_mod inst_name (.port(net), ...)
            for other_mod in module_names:
                if other_mod == parent_module: continue
                
                # Find all instantiations of other_mod within parent_module
                # Pattern: module_name #(params) instance_name (port_connections);
                inst_pattern = r'\b' + re.escape(other_mod) + r'\s+(?:#\s*\((.*?)\)\s*)?(\w+)\s*\((.*?)\);'
                matches = list(re.finditer(inst_pattern, clean_body, re.DOTALL | re.MULTILINE))
                
                if matches:
                    # Create DEPENDS_ON edge with metadata about instances
                    instance_names = [m.group(2) for m in matches]
                    edge_key = get_edge_key(parent_module, other_mod, EDGE_DEPENDS_ON)
                    edges.append({
                        "_key": edge_key,
                        "from": parent_module,
                        "to": other_mod,
                        "type": EDGE_DEPENDS_ON,
                        "instance_count": len(instance_names),
                        "instance_names": instance_names[:10],  # Cap at 10 to avoid bloat
                        "source_file": fname
                    })
                    dependencies_count += 1

                    # Extract Parameter Overrides
                    for m in matches:
                        params_content = m.group(1)
                        instance_name = m.group(2)
                        if params_content:
                            # Extract (.PARAM(value)) mappings
                            param_pattern = r'\.\s*(\w+)\s*\(\s*([^)]+)\s*\)'
                            for p_match in re.finditer(param_pattern, params_content):
                                param_name = p_match.group(1).strip()
                                param_value = p_match.group(2).strip()
                                
                                # The target is the parameter node in the child module
                                param_id = sanitize_id(f"{other_mod}.{param_name}")
                                
                                edges.append({
                                    "_key": get_edge_key(f"{parent_module}.{instance_name}", param_id, EDGE_OVERRIDES),
                                    "from": parent_module, # The module containing the instantiation
                                    "to": param_id,
                                    "type": EDGE_OVERRIDES,
                                    "metadata": {
                                        "instance": instance_name,
                                        "value": param_value,
                                        "child_module": other_mod
                                    }
                                })
    
    print(f"  Found {dependencies_count} module dependencies")

    # Pass 4: Extract Pin-to-Pin Connectivity (WIRED_TO)
    print("Extracting Pin-to-Pin connectivity...")
    
    # Pre-build a map of valid module ports for validation
    # module_name -> set of port_names
    valid_module_ports = {}
    for node in nodes:
        if node['type'] == COL_PORT:
            # port_id is "module.port"
            parts = node['id'].split('.')
            if len(parts) == 2:
                mname, pname = parts
                if mname not in valid_module_ports:
                    valid_module_ports[mname] = set()
                valid_module_ports[mname].add(pname)

    for fname, content in file_map.items():
        for parent_module, module_body in VerilogParser.get_module_bodies(content):
            clean_body = re.sub(r'/\*.*?\*/', ' ', module_body, flags=re.DOTALL)
            
            # net_map local to this module's context
            net_map = {} # net_name -> list of (module_id, port_name)
            
            # Look for instantiations: other_mod inst_name (.port(net), ...)
            for other_mod in module_names:
                if other_mod == parent_module: continue
                
                # Find all instantiations of other_mod
                inst_pattern = r'\b' + re.escape(other_mod) + r'\s+(?:#\s*\((.*?)\)\s*)?(\w+)\s*\((.*?)\);'
                for inst_match in re.finditer(inst_pattern, clean_body, re.DOTALL | re.MULTILINE):
                    pins_content = inst_match.group(3)
                    
                    # Extract (.port(net)) mappings
                    pin_pattern = r'\.\s*(\w+)\s*\(\s*([^)]+)\s*\)'
                    for pin_match in re.finditer(pin_pattern, pins_content):
                        port_name = pin_match.group(1)
                        
                        # VALIDATION: Check if port actually exists in other_mod
                        if other_mod in valid_module_ports and port_name not in valid_module_ports[other_mod]:
                            # Skip connection to non-existent port (handles commented out ports in RTL)
                            continue

                        net_name_raw = pin_match.group(2).strip()
                        net_name = net_name_raw.split('[')[0].strip()
                        
                        if net_name not in net_map:
                            net_map[net_name] = []
                        net_map[net_name].append((other_mod, port_name))

            # Create WIRED_TO edges for all ports sharing the same net within THIS module
            # Filter high-fanout nets to prevent combinatorial explosion (hairballs)
            NET_BLACKLIST = {'clk', 'clk_i', 'clk_o', 'rst', 'rst_i', 'rst_n', 'reset', 'gnd', 'vcc'}
            
            for net, connections in net_map.items():
                if len(connections) < 2:
                    continue
                
                # Skip blacklisted or extremely high fanout nets
                if net.lower() in NET_BLACKLIST or len(connections) > 20:
                    continue
                    
                # Create an edge between every pair of ports on this net
                for i in range(len(connections)):
                    for j in range(i + 1, len(connections)):
                        m1, p1 = connections[i]
                        m2, p2 = connections[j]
                        
                        port1_id = sanitize_id(f"{m1}.{p1}")
                        port2_id = sanitize_id(f"{m2}.{p2}")
                        
                        # Sort IDs to ensure (A,B) and (B,A) get the same key if they ever clash
                        c1, c2 = sorted([port1_id, port2_id])
                        
                        edges.append({
                            "_key": get_edge_key(c1, c2, EDGE_WIRED_TO),
                            "from": port1_id,
                            "to": port2_id,
                            "type": EDGE_WIRED_TO,
                            "metadata": {"net": net, "context": parent_module}
                        })

    with open(RTL_NODES_FILE, 'w') as f:
        json.dump(nodes, f, indent=2)
        
    with open(RTL_EDGES_FILE, 'w') as f:
        json.dump(edges, f, indent=2)

    print(f"RTL Extraction Complete. {len(nodes)} nodes, {len(edges)} edges.")

if __name__ == "__main__":
    parse_verilog_files()
