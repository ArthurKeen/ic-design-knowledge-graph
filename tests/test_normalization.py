import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'src'))
from utils import normalize_hardware_name

def test_normalize_basic():
    assert normalize_hardware_name("OR1200_ALU") == "alu"
    assert normalize_hardware_name("or1200_dmmu") == "dmmu"

def test_normalize_with_underscores():
    assert normalize_hardware_name("or1200_except_top") == "except top"

def test_normalize_with_dots():
    assert normalize_hardware_name("or1200_alu.result") == "result"
    assert normalize_hardware_name("module.sub.signal") == "signal"

def test_normalize_empty():
    assert normalize_hardware_name("") == ""
    assert normalize_hardware_name(None) == ""

def test_normalize_mixed_case():
    assert normalize_hardware_name("Or1200_PIC") == "pic"
