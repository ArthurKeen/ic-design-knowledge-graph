import sys
import os
import re
sys.path.append(os.path.join(os.getcwd(), 'src'))
from etl_rtl import RE_MODULE, RE_INPUT, RE_ALWAYS

def test_regex_module():
    content = """  module or1200_alu ( clk, rst );
    // module body
endmodule"""
    match = RE_MODULE.search(content)
    assert match is not None
    assert match.group(1) == "or1200_alu"

def test_regex_input():
    content = "  input clk, rst;\n  input [31:0] data_i;"
    matches = list(RE_INPUT.finditer(content))
    assert len(matches) == 2
    # group(1) is the optional width specifier; group(2) is the signal name(s)
    assert "clk" in matches[0].group(2)
    assert "data_i" in matches[1].group(2)

def test_regex_always():
    content = """
    always @(posedge clk) begin
        if (rst) result <= 0;
        else result <= a + b;
    end
    """
    match = RE_ALWAYS.search(content)
    assert match is not None
    assert "posedge clk" in match.group(0)
