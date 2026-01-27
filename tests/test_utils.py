import os
import json
import pytest
import shutil
import tempfile
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from utils import (
    sanitize_id, 
    get_edge_key, 
    normalize_hardware_name, 
    strip_comments, 
    expand_acronym, 
    VerilogParser, 
    NodeResolver
)

def test_sanitize_id():
    assert sanitize_id("clk") == "clk"
    assert sanitize_id("reg [31:0] data") == "31:0_data"
    assert sanitize_id("input clk") == "clk"
    assert sanitize_id("output [7:0] q") == "7:0_q"
    assert sanitize_id("assign out = in;") == "out_in" # assign removed, = and ; replaced by _
    # Re-checking sanitize_id logic: 
    # re.sub(r'\b(reg|wire|input|output|assign)\b', '', raw_id)
    # re.sub(r'[\s\t\n\r]+', '', clean)
    # re.sub(r'[^a-zA-Z0-9_\-:\.]', '_', clean)
    assert sanitize_id("module.sub_item[0]") == "module.sub_item_0"
    assert sanitize_id("") == ""
    assert sanitize_id(None) == ""

def test_get_edge_key():
    k1 = get_edge_key("A", "B", "TYPE")
    k2 = get_edge_key("A", "B", "TYPE")
    k3 = get_edge_key("B", "A", "TYPE")
    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 32 # MD5 hash length

def test_normalize_hardware_name():
    assert normalize_hardware_name("OR1200_ALU") == "alu"
    assert normalize_hardware_name("or1200_alu_ctrl") == "alu ctrl"
    assert normalize_hardware_name("module.sub_signal") == "sub signal"
    assert normalize_hardware_name("signal_name") == "signal name"
    assert normalize_hardware_name("") == ""
    assert normalize_hardware_name(None) == ""

def test_strip_comments():
    code = "assign a = b; // single line\n/* multi\nline */ assign c = d;"
    expected = "assign a = b; \n assign c = d;"
    assert strip_comments(code).strip() == expected.strip()

def test_expand_acronym():
    acronyms = {"insn": "Instruction", "if": "Instruction Fetch"}
    assert expand_acronym("if_insn", acronyms) == "Instruction Fetch Instruction"
    assert expand_acronym("clk", acronyms) is None
    assert expand_acronym("InsnControl", acronyms) == "Instruction Control"
    assert expand_acronym("", acronyms) is None

def test_verilog_parser():
    content = """
    module mod1 (clk);
      input clk;
    endmodule
    
    module mod2 #(parameter P=1) (out);
      output out;
    endmodule
    """
    bodies = list(VerilogParser.get_module_bodies(content))
    assert len(bodies) == 2
    assert bodies[0][0] == "mod1"
    assert "input clk;" in bodies[0][1]
    assert bodies[1][0] == "mod2"
    assert "parameter P=1" in bodies[1][1]

class TestNodeResolver:
    @pytest.fixture
    def mock_data_dir(self):
        # Setup temporary directory with mock JSON files
        temp_dir = tempfile.mkdtemp()
        
        rtl_nodes = [
            {"id": "mod1.clk", "type": "RTL_Port"},
            {"id": "mod1.sig_data", "type": "RTL_Signal"},
            {"id": "mod1", "type": "RTL_Module"}
        ]
        with open(os.path.join(temp_dir, 'rtl_nodes.json'), 'w') as f:
            json.dump(rtl_nodes, f)
            
        mem_nodes = [
            {"id": "mod1.ram_block", "type": "RTL_Memory"}
        ]
        with open(os.path.join(temp_dir, 'memory_nodes.json'), 'w') as f:
            json.dump(mem_nodes, f)
            
        param_nodes = [
            {"id": "mod1.WIDTH", "type": "RTL_Parameter", "name": "WIDTH"},
            {"id": "GLOBAL.MAX_VAL", "type": "RTL_Parameter", "name": "MAX_VAL"}
        ]
        with open(os.path.join(temp_dir, 'param_nodes.json'), 'w') as f:
            json.dump(param_nodes, f)
            
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_resolve_port(self, mock_data_dir):
        resolver = NodeResolver(mock_data_dir)
        assert resolver.resolve_id("mod1", "clk") == "mod1.clk"

    def test_resolve_signal(self, mock_data_dir):
        resolver = NodeResolver(mock_data_dir)
        # Note: input "data" should resolve to "mod1.sig_data"
        assert resolver.resolve_id("mod1", "data") == "mod1.sig_data"

    def test_resolve_memory(self, mock_data_dir):
        resolver = NodeResolver(mock_data_dir)
        assert resolver.resolve_id("mod1", "ram_block") == "mod1.ram_block"

    def test_resolve_parameter(self, mock_data_dir):
        resolver = NodeResolver(mock_data_dir)
        assert resolver.resolve_id("mod1", "WIDTH") == "mod1.WIDTH"

    def test_resolve_global_parameter(self, mock_data_dir):
        resolver = NodeResolver(mock_data_dir)
        assert resolver.resolve_id("mod1", "MAX_VAL") == "GLOBAL.MAX_VAL"

    def test_resolve_module(self, mock_data_dir):
        resolver = NodeResolver(mock_data_dir)
        assert resolver.resolve_id("other_mod", "mod1") == "mod1"

    def test_resolve_fallback(self, mock_data_dir):
        resolver = NodeResolver(mock_data_dir)
        # Unknown name should return module_id.name as default port-style ID
        assert resolver.resolve_id("mod1", "unknown") == "mod1.unknown"
