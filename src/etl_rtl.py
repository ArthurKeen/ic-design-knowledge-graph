"""
src/etl_rtl.py — Multi-repo Verilog/SystemVerilog RTL extractor.

Parses RTL source files to extract the structural property graph:
  Vertices: RTL_Module, RTL_Port, RTL_Signal, RTL_LogicChunk, RTL_Assign, RTL_Parameter
  Edges:    CONTAINS, HAS_PORT, HAS_SIGNAL, DEPENDS_ON, WIRED_TO, OVERRIDES

Writes directly to ArangoDB (upsert) when a db handle is provided,
or falls back to JSON files for standalone / dry-run use.

Usage (standalone):
    python etl_rtl.py

Usage (programmatic, multi-repo):
    from etl_rtl import parse_verilog_files
    summary = parse_verilog_files(
        rtl_dir="path/to/ibex/rtl",
        prefix="IBEX_",
        db=arango_db_handle,
        rtl_extensions=[".sv", ".v"],
    )
"""

import os
import re
import json
import sys
import hashlib

# ---------------------------------------------------------------------------
# Config / path setup
# ---------------------------------------------------------------------------
_pkg_root = os.path.dirname(os.path.abspath(__file__))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from config import (
    RTL_DIR, RTL_NODES_FILE, RTL_EDGES_FILE,
    COL_MODULE, COL_PORT, COL_SIGNAL, COL_LOGIC,
    EDGE_HAS_PORT, EDGE_HAS_SIGNAL, EDGE_CONTAINS, EDGE_WIRED_TO,
    EDGE_DEPENDS_ON, EDGE_OVERRIDES,
)
from utils import sanitize_id, get_edge_key, VerilogParser, strip_comments, expand_acronym

# Load default acronym dictionary (OR1200-specific; other repos fall back to empty)
_DEFAULT_ACRONYM_DICT = {}
try:
    _acronym_path = os.path.join(_pkg_root, "or1200_acronyms.json")
    with open(_acronym_path) as f:
        _DEFAULT_ACRONYM_DICT = json.load(f)
    print(f"[etl_rtl] Loaded {len(_DEFAULT_ACRONYM_DICT)} acronym mappings")
except FileNotFoundError:
    pass

# ---------------------------------------------------------------------------
# Regex patterns — Verilog and SystemVerilog
# ---------------------------------------------------------------------------
RE_MODULE   = re.compile(r'^\s*module\s+(\w+)\s*[(\s#]', re.MULTILINE)
RE_INPUT    = re.compile(r'^\s*input\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[([^\]]*)\]\s*)?([^;]+);(?:\s*//(.*))?', re.MULTILINE)
RE_OUTPUT   = re.compile(r'^\s*output\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[([^\]]*)\]\s*)?([^;]+);(?:\s*//(.*))?', re.MULTILINE)
RE_SIGNALS  = re.compile(r'^\s*(wire|reg|logic)\s+(?:\[([^\]]*)\]\s*)?([^;]+);(?:\s*//(.*))?', re.MULTILINE)
# always, always_ff, always_comb, always_latch
RE_ALWAYS   = re.compile(r'^\s*always(?:_ff|_comb|_latch)?\s*(?:@\s*\(.*?\)\s*)?(?:begin\b.*?end\b|[^;]*?;)', re.MULTILINE | re.DOTALL)
RE_ASSIGN   = re.compile(r'^\s*assign\s+.*?;', re.MULTILINE)
RE_PARAM    = re.compile(r'^\s*(?:parameter|localparam)\s+(?:\[([^\]]*)\]\s*)?(\w+)\s*=\s*([^;]+);(?:\s*//(.*))?', re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:16]


def _find_comment_above(lines: list[str], line_idx: int) -> str:
    for i in range(line_idx - 1, max(-1, line_idx - 5), -1):
        line = lines[i].strip()
        if line.startswith("//"):
            return line[2:].strip()
        if line.endswith("*/"):
            return line.replace("*/", "").replace("/*", "").replace("*", "").strip()
        if line and not line.startswith("/"):
            break
    return ""


def _module_summary(content: str, module_body: str) -> str:
    """Best-effort extraction of a module's description from surrounding comments."""
    patterns = [
        # Standard "Description" block
        r'Description\s*/*\n\s*(?:/{2,4}\s*)(.*?)\n\s*(?:/{2,4}\s*)\n',
        r'Description\s*:?\s*(.*?)(?:\n\s*\n|\*/|Author)',
        r'/{2,4}\s*(OR1200.*?)\s*/{2,4}',
    ]
    for pat in patterns:
        m = re.search(pat, content, re.DOTALL | re.IGNORECASE)
        if m:
            raw = m.group(1)
            lines = [re.sub(r'^[\s/*]+|[\s/*]+$', '', l).strip() for l in raw.split("\n")]
            s = " ".join(l for l in lines if l).strip()
            if s:
                return s
    # Fallback: first comment lines inside module
    for line in module_body.splitlines()[:10]:
        line = line.strip()
        if line.startswith("//"):
            return line[2:].strip()
    return ""


def _bulk_upsert(db, col_name: str, docs: list[dict], edge: bool = False) -> None:
    """Upsert a batch of documents into an ArangoDB collection."""
    if not docs:
        return
    if not db.has_collection(col_name):
        if edge:
            db.create_collection(col_name, edge=True)
            print(f"  [etl_rtl] Created edge collection: {col_name}")
        else:
            db.create_collection(col_name)
            print(f"  [etl_rtl] Created vertex collection: {col_name}")

    col = db.collection(col_name)
    # Use AQL for upsert — handles conflicts gracefully
    db.aql.execute(
        "FOR doc IN @docs INSERT doc INTO @@col OPTIONS {overwriteMode: 'update'} LET x = 1 RETURN x",
        bind_vars={"docs": docs, "@col": col_name},
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_verilog_files(
    rtl_dir:        str       = None,
    prefix:         str       = "OR1200_",
    db                        = None,
    dry_run:        bool      = False,
    rtl_extensions: list[str] = None,
    acronym_dict:   dict      = None,
) -> dict:
    """
    Parse Verilog/SystemVerilog files and extract the RTL property graph.

    Args:
        rtl_dir:        Directory containing .v / .sv files. Defaults to OR1200 RTL_DIR.
        prefix:         Repo prefix for _key namespacing (e.g. "IBEX_"). Used only for _key
                        generation; collections are SHARED (RTL_Module, RTL_Port, etc.).
        db:             ArangoDB database handle. If provided, upserts directly.
                        If None, writes JSON files (legacy behaviour).
        dry_run:        If True, parses but does not write anything.
        rtl_extensions: File extensions to process. Default: [".v"].
        acronym_dict:   Acronym expansion dictionary. Default: or1200_acronyms.json.

    Returns:
        Summary dict: {modules, ports, signals, logic_chunks, parameters, edges}
    """
    rtl_dir        = rtl_dir        or RTL_DIR
    rtl_extensions = rtl_extensions or [".v"]
    acronym_dict   = acronym_dict   or _DEFAULT_ACRONYM_DICT
    repo           = prefix.rstrip("_")

    print(f"[etl_rtl] Scanning: {rtl_dir}  (prefix={prefix}, extensions={rtl_extensions})")

    # Collect files
    files = [
        f for f in os.listdir(rtl_dir)
        if any(f.endswith(ext) for ext in rtl_extensions)
    ]
    if not files:
        print(f"[etl_rtl] WARNING: No RTL files found in {rtl_dir}")
        return {"modules": 0, "ports": 0, "signals": 0, "logic_chunks": 0, "parameters": 0, "edges": 0}

    print(f"[etl_rtl] Found {len(files)} RTL files")

    # -----------------------------------------------------------------------
    # Pass 1: collect all module names (needed for CONTAINS / DEPENDS_ON)
    # -----------------------------------------------------------------------
    module_names: set[str] = set()
    file_map:    dict[str, str] = {}

    for fname in files:
        path = os.path.join(rtl_dir, fname)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError as e:
            print(f"[etl_rtl] WARNING: Cannot read {fname}: {e}")
            continue
        file_map[fname] = content
        for mod_name, _ in VerilogParser.get_module_bodies(content):
            module_names.add(mod_name)

    print(f"[etl_rtl] Pass 1 complete — {len(module_names)} modules identified")

    # -----------------------------------------------------------------------
    # Pass 2: extract details per module
    # -----------------------------------------------------------------------
    nodes:  list[dict] = []
    edges:  list[dict] = []
    counts = {"modules": 0, "ports": 0, "signals": 0, "logic_chunks": 0, "parameters": 0}

    for fname, content in file_map.items():
        for current_module, module_body in VerilogParser.get_module_bodies(content):
            clean_body   = re.sub(r'/\*.*?\*/', ' ', module_body, flags=re.DOTALL)
            module_lines = clean_body.splitlines()
            summary      = _module_summary(content, module_body)
            expanded     = expand_acronym(current_module, acronym_dict)
            mod_key      = f"{prefix}{sanitize_id(current_module)}"

            nodes.append({
                "_key":         mod_key,
                "name":         current_module,
                "type":         "RTL_Module",
                "labels":       ["RTLModule", repo],
                "repo":         repo,
                "layer":        "rtl",
                "file":         fname,
                "summary":      summary,
                "expanded_name": expanded,
                "code_content": module_body[:2000],   # truncate to avoid huge docs
            })
            counts["modules"] += 1

            # ---- Ports (input / output) ------------------------------------
            seen_ports: set[str] = set()

            for direction, pattern in [("input", RE_INPUT), ("output", RE_OUTPUT)]:
                for match in pattern.finditer(clean_body):
                    width_expr   = (match.group(1) or "").strip()
                    raw_ports    = strip_comments(match.group(2))
                    inline_comment = (match.group(3) or "").strip()
                    if not inline_comment:
                        line_idx = clean_body[:match.start()].count("\n")
                        inline_comment = _find_comment_above(module_lines, line_idx)

                    for p in raw_ports.split(","):
                        p_clean = sanitize_id(p.strip())
                        if not p_clean or p_clean in seen_ports:
                            continue
                        seen_ports.add(p_clean)
                        port_id  = f"{current_module}.{p_clean}"
                        port_key = f"{prefix}{sanitize_id(port_id)}"

                        nodes.append({
                            "_key":          port_key,
                            "name":          p_clean,
                            "type":          "RTL_Port",
                            "labels":        ["RTLPort", direction, repo],
                            "repo":          repo,
                            "layer":         "rtl",
                            "parent_module": current_module,
                            "direction":     direction,
                            "description":   inline_comment,
                            "expanded_name": expand_acronym(p_clean, acronym_dict),
                            "width_expr":    width_expr,
                        })
                        edges.append({
                            "_key":         get_edge_key(mod_key, port_key, EDGE_HAS_PORT),
                            "_from":        f"RTL_Module/{mod_key}",
                            "_to":          f"RTL_Port/{port_key}",
                            "type":         "HAS_PORT",
                            "labels":       ["HAS_PORT"],
                            "fromNodeType": "RTLModule",
                            "toNodeType":   "RTLPort",
                            "repo":         repo,
                        })
                        counts["ports"] += 1

            # ---- Internal signals (wire / reg / logic) ----------------------
            sig_seen: set[str] = set()
            for match in RE_SIGNALS.finditer(clean_body):
                sig_type   = match.group(1)
                width_expr = (match.group(2) or "").strip()
                raw_sigs   = strip_comments(match.group(3))
                inline_comment = (match.group(4) or "").strip()
                if not inline_comment:
                    line_idx = clean_body[:match.start()].count("\n")
                    inline_comment = _find_comment_above(module_lines, line_idx)

                for s in raw_sigs.split(","):
                    s = s.strip()
                    if "=" in s:
                        s = s.split("=")[0].strip()
                    s_clean = sanitize_id(s)
                    if not s_clean or s_clean in sig_seen:
                        continue
                    sig_seen.add(s_clean)
                    sig_id  = f"{current_module}.sig_{s_clean}"
                    sig_key = f"{prefix}{sanitize_id(sig_id)}"

                    nodes.append({
                        "_key":          sig_key,
                        "name":          s_clean,
                        "type":          "RTL_Signal",
                        "labels":        ["RTLSignal", sig_type, repo],
                        "repo":          repo,
                        "layer":         "rtl",
                        "parent_module": current_module,
                        "datatype":      sig_type,
                        "description":   inline_comment,
                        "expanded_name": expand_acronym(s_clean, acronym_dict),
                        "width_expr":    width_expr,
                    })
                    edges.append({
                        "_key":         get_edge_key(mod_key, sig_key, EDGE_HAS_SIGNAL),
                        "_from":        f"RTL_Module/{mod_key}",
                        "_to":          f"RTL_Signal/{sig_key}",
                        "type":         "HAS_SIGNAL",
                        "labels":       ["HAS_SIGNAL"],
                        "fromNodeType": "RTLModule",
                        "toNodeType":   "RTLSignal",
                        "repo":         repo,
                    })
                    counts["signals"] += 1

            # ---- Parameters ------------------------------------------------
            for match in RE_PARAM.finditer(clean_body):
                p_name    = match.group(2)
                p_value   = (match.group(3) or "").strip()
                p_comment = (match.group(4) or "").strip()
                param_key = f"{prefix}{sanitize_id(current_module + '.' + p_name)}"
                nodes.append({
                    "_key":          param_key,
                    "name":          p_name,
                    "type":          "RTL_Parameter",
                    "labels":        ["RTLParameter", repo],
                    "repo":          repo,
                    "layer":         "rtl",
                    "parent_module": current_module,
                    "default_value": p_value[:100],
                    "description":   p_comment,
                })
                edges.append({
                    "_key":         get_edge_key(mod_key, param_key, "HAS_PARAMETER"),
                    "_from":        f"RTL_Module/{mod_key}",
                    "_to":          f"RTL_Parameter/{param_key}",
                    "type":         "HAS_PARAMETER",
                    "labels":       ["HAS_PARAMETER"],
                    "fromNodeType": "RTLModule",
                    "toNodeType":   "RTLParameter",
                    "repo":         repo,
                })
                counts["parameters"] += 1

            # ---- Logic chunks (always / assign) ----------------------------
            for idx, match in enumerate(RE_ALWAYS.finditer(clean_body)):
                block_code = match.group(0).strip()
                chunk_id   = f"{current_module}.always_{idx}"
                chunk_key  = f"{prefix}{sanitize_id(chunk_id)}"
                nodes.append({
                    "_key":          chunk_key,
                    "name":          f"{current_module}_always_{idx}",
                    "type":          "RTL_LogicChunk",
                    "labels":        ["RTLLogicChunk", "AlwaysBlock", repo],
                    "repo":          repo,
                    "layer":         "rtl",
                    "parent_module": current_module,
                    "chunk_type":    "always_block",
                    "code":          block_code[:500],
                })
                edges.append({
                    "_key":         get_edge_key(mod_key, chunk_key, EDGE_CONTAINS),
                    "_from":        f"RTL_Module/{mod_key}",
                    "_to":          f"RTL_LogicChunk/{chunk_key}",
                    "type":         "CONTAINS",
                    "labels":       ["CONTAINS"],
                    "fromNodeType": "RTLModule",
                    "toNodeType":   "RTLLogicChunk",
                    "repo":         repo,
                })
                counts["logic_chunks"] += 1

            for idx, match in enumerate(RE_ASSIGN.finditer(clean_body)):
                assign_code = match.group(0).strip()
                assign_id   = f"{current_module}.assign_{idx}"
                assign_key  = f"{prefix}{sanitize_id(assign_id)}"
                nodes.append({
                    "_key":          assign_key,
                    "name":          f"{current_module}_assign_{idx}",
                    "type":          "RTL_LogicChunk",
                    "labels":        ["RTLLogicChunk", "AssignStatement", repo],
                    "repo":          repo,
                    "layer":         "rtl",
                    "parent_module": current_module,
                    "chunk_type":    "assign_statement",
                    "code":          assign_code[:200],
                })
                edges.append({
                    "_key":         get_edge_key(mod_key, assign_key, EDGE_CONTAINS),
                    "_from":        f"RTL_Module/{mod_key}",
                    "_to":          f"RTL_LogicChunk/{assign_key}",
                    "type":         "CONTAINS",
                    "labels":       ["CONTAINS"],
                    "fromNodeType": "RTLModule",
                    "toNodeType":   "RTLLogicChunk",
                    "repo":         repo,
                })
                counts["logic_chunks"] += 1

    # -----------------------------------------------------------------------
    # Pass 3: module dependencies (DEPENDS_ON) and parameter overrides
    # -----------------------------------------------------------------------
    print(f"[etl_rtl] Pass 2 complete — extracting dependencies …")
    dep_count = 0

    for fname, content in file_map.items():
        for parent_module, module_body in VerilogParser.get_module_bodies(content):
            clean_body = re.sub(r'/\*.*?\*/', ' ', module_body, flags=re.DOTALL)
            parent_key = f"{prefix}{sanitize_id(parent_module)}"

            for other_mod in module_names:
                if other_mod == parent_module:
                    continue
                inst_pattern = (
                    r'\b' + re.escape(other_mod) +
                    r'\s+(?:#\s*\((.*?)\)\s*)?(\w+)\s*\((.*?)\);'
                )
                matches = list(re.finditer(inst_pattern, clean_body, re.DOTALL | re.MULTILINE))
                if not matches:
                    continue

                other_key      = f"{prefix}{sanitize_id(other_mod)}"
                instance_names = [m.group(2) for m in matches]
                edges.append({
                    "_key":           get_edge_key(parent_key, other_key, EDGE_DEPENDS_ON),
                    "_from":          f"RTL_Module/{parent_key}",
                    "_to":            f"RTL_Module/{other_key}",
                    "type":           "DEPENDS_ON",
                    "labels":         ["DEPENDS_ON"],
                    "fromNodeType":   "RTLModule",
                    "toNodeType":     "RTLModule",
                    "repo":           repo,
                    "instance_count": len(instance_names),
                    "instance_names": instance_names[:10],
                    "source_file":    fname,
                })
                dep_count += 1

                # Parameter overrides
                for m in matches:
                    if not m.group(1):
                        continue
                    for p_match in re.finditer(r'\.\s*(\w+)\s*\(\s*([^)]+)\s*\)', m.group(1)):
                        p_name  = p_match.group(1).strip()
                        p_value = p_match.group(2).strip()
                        param_id  = sanitize_id(f"{other_mod}.{p_name}")
                        param_key = f"{prefix}{param_id}"
                        edges.append({
                            "_key":         get_edge_key(f"{parent_key}.{m.group(2)}", param_key, EDGE_OVERRIDES),
                            "_from":        f"RTL_Module/{parent_key}",
                            "_to":          f"RTL_Parameter/{param_key}",
                            "type":         "OVERRIDES",
                            "labels":       ["OVERRIDES"],
                            "fromNodeType": "RTLModule",
                            "toNodeType":   "RTLParameter",
                            "repo":         repo,
                            "instance":     m.group(2),
                            "value":        p_value,
                            "child_module": other_mod,
                        })

    print(f"[etl_rtl] {dep_count} dependency edges")

    # -----------------------------------------------------------------------
    # Pass 4: pin-to-pin wiring (WIRED_TO)
    # -----------------------------------------------------------------------
    print(f"[etl_rtl] Extracting WIRED_TO edges …")

    # Build port key lookup: module_name → set of port_names
    valid_module_ports: dict[str, set[str]] = {}
    for node in nodes:
        if node["type"] == "RTL_Port":
            mod  = node["parent_module"]
            name = node["name"]
            valid_module_ports.setdefault(mod, set()).add(name)

    NET_BLACKLIST = {"clk", "clk_i", "clk_o", "rst", "rst_i", "rst_n", "reset", "gnd", "vcc"}
    wire_count = 0

    for fname, content in file_map.items():
        for parent_module, module_body in VerilogParser.get_module_bodies(content):
            clean_body = re.sub(r'/\*.*?\*/', ' ', module_body, flags=re.DOTALL)
            net_map: dict[str, list[tuple[str, str]]] = {}

            for other_mod in module_names:
                if other_mod == parent_module:
                    continue
                inst_pattern = (
                    r'\b' + re.escape(other_mod) +
                    r'\s+(?:#\s*\(.*?\)\s*)?(\w+)\s*\((.*?)\);'
                )
                for inst_match in re.finditer(inst_pattern, clean_body, re.DOTALL | re.MULTILINE):
                    pins_content = inst_match.group(2)
                    for pin_match in re.finditer(r'\.\s*(\w+)\s*\(\s*([^)]+)\s*\)', pins_content):
                        port_name = pin_match.group(1)
                        if other_mod in valid_module_ports and port_name not in valid_module_ports[other_mod]:
                            continue
                        net_name = pin_match.group(2).strip().split("[")[0].strip()
                        net_map.setdefault(net_name, []).append((other_mod, port_name))

            for net, connections in net_map.items():
                if len(connections) < 2:
                    continue
                if net.lower() in NET_BLACKLIST or len(connections) > 20:
                    continue
                for i in range(len(connections)):
                    for j in range(i + 1, len(connections)):
                        m1, p1 = connections[i]
                        m2, p2 = connections[j]
                        k1 = f"{prefix}{sanitize_id(f'{m1}.{p1}')}"
                        k2 = f"{prefix}{sanitize_id(f'{m2}.{p2}')}"
                        c1, c2 = sorted([k1, k2])
                        edges.append({
                            "_key":         get_edge_key(c1, c2, EDGE_WIRED_TO),
                            "_from":        f"RTL_Port/{c1}",
                            "_to":          f"RTL_Port/{c2}",
                            "type":         "WIRED_TO",
                            "labels":       ["WIRED_TO"],
                            "fromNodeType": "RTLPort",
                            "toNodeType":   "RTLPort",
                            "repo":         repo,
                            "net":          net,
                            "context":      parent_module,
                        })
                        wire_count += 1

    print(f"[etl_rtl] {wire_count} WIRED_TO edges")
    counts["edges"] = len(edges)

    # -----------------------------------------------------------------------
    # Write output
    # -----------------------------------------------------------------------
    if dry_run:
        print(f"[etl_rtl] DRY RUN — {counts['modules']} modules, {counts['ports']} ports, "
              f"{counts['signals']} signals, {counts['logic_chunks']} logic chunks, "
              f"{len(edges)} edges (not written)")
        return counts

    if db is not None:
        # Bucket nodes by collection type
        by_col: dict[str, list[dict]] = {}
        for node in nodes:
            col = node["type"].replace("_", "")  # e.g. "RTL_Module" → "RTLModule"
            # ArangoDB collection name stays underscore-style
            col_name = node["type"]              # "RTL_Module", "RTL_Port", etc.
            by_col.setdefault(col_name, []).append(node)

        for col_name, docs in by_col.items():
            print(f"  {col_name:35s} {len(docs):6d}")
            _bulk_upsert(db, col_name, docs, edge=False)

        # Bucket edges by type
        edge_col_map = {
            "CONTAINS":     "CONTAINS",
            "HAS_PORT":     "HAS_PORT",
            "HAS_SIGNAL":   "HAS_SIGNAL",
            "HAS_PARAMETER":"HAS_PARAMETER",
            "DEPENDS_ON":   "DEPENDS_ON",
            "OVERRIDES":    "OVERRIDES",
            "WIRED_TO":     "WIRED_TO",
        }
        by_edge_col: dict[str, list[dict]] = {}
        for edge in edges:
            col_name = edge_col_map.get(edge["type"], "RTL_Relations")
            by_edge_col.setdefault(col_name, []).append(edge)

        for col_name, docs in by_edge_col.items():
            print(f"  {col_name:35s} {len(docs):6d}")
            _bulk_upsert(db, col_name, docs, edge=True)

        print(f"[etl_rtl] Done — {sum(len(d) for d in by_col.values())} nodes, "
              f"{len(edges)} edges written to ArangoDB")
    else:
        # Legacy JSON file output (OR1200 standalone usage)
        # Reformat to match old schema expected by downstream scripts
        json_nodes = [
            {"id": n["name"], "label": n["name"], "type": n["type"],
             "metadata": {k: v for k, v in n.items() if k not in ("_key", "name", "type")}}
            for n in nodes
        ]
        json_edges = [
            {"_key": e["_key"], "from": e["_from"].split("/")[-1],
             "to": e["_to"].split("/")[-1], "type": e["type"]}
            for e in edges
        ]
        with open(RTL_NODES_FILE, "w") as f:
            json.dump(json_nodes, f, indent=2)
        with open(RTL_EDGES_FILE, "w") as f:
            json.dump(json_edges, f, indent=2)
        print(f"[etl_rtl] Done — {len(json_nodes)} nodes, {len(json_edges)} edges → JSON files")

    return counts


# ---------------------------------------------------------------------------
# Standalone entry point (OR1200 legacy behaviour)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parse_verilog_files()
