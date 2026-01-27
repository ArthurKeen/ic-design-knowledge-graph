#!/usr/bin/env python3
"""
Master ETL Script for Integrated Circuit (IC) Design Knowledge Graph
========================================

This script orchestrates the entire ETL pipeline:
1.  Executes all extractor scripts (RTL, Git, FSM, etc.) to generate JSON data.
2.  Loads the generated JSON data into ArangoDB using `src/load_data.py`.
3.  Runs direct-to-DB extractors (e.g., Authors).
4.  Runs semantic consolidation and bridging.

Usage:
    python scripts/master_etl.py
"""

import os
import sys
import subprocess
import time
from datetime import datetime

# Ensure we're in the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.append(SRC_DIR)

def run_script(script_name, cwd=PROJECT_ROOT):
    """Run a python script and check for errors."""
    script_path = os.path.join("src", script_name) if not script_name.startswith("scripts/") else script_name
    print(f"\n[MASTER] Running {script_name}...")
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, script_path], 
            cwd=cwd,
            check=True,
            text=True
        )
        duration = time.time() - start_time
        print(f"[MASTER] ✓ {script_name} completed in {duration:.2f}s")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[MASTER] ❌ Error executing {script_name}: {e}")
        return False

def main():
    print("="*80)
    print(f"IC KNOWLEDGE GRAPH - MASTER ETL PIPELINE")
    print(f"Started at: {datetime.now().isoformat()}")
    print("="*80)

    # ---------------------------------------------------------
    # Stage 1: Extraction (Generates JSON files in data/)
    # ---------------------------------------------------------
    print("\n" + "="*40)
    print("STAGE 1: EXTRACTORS (Generate JSON)")
    print("="*40)
    
    extractors = [
        "etl_rtl.py",           # Core RTL (Modules, Ports, Signals)
        "etl_git.py",           # Git History
        "etl_bus.py",           # Bus Interfaces
        "etl_fsm.py",           # State Machines
        "etl_always.py",        # Always Blocks
        "etl_assigns.py",       # Assignments
        "etl_assertions.py",    # Assertions
        "etl_clocks.py",        # Clock Domains
        "etl_functions.py",     # Functions
        "etl_generate.py",      # Generate Blocks
        "etl_memory_access.py", # Memory Access
        "etl_operators.py",     # Operations
        "etl_params_memory.py", # Parameters & Memories
        "etl_calls.py"          # Function Calls
    ]
    
    for script in extractors:
        if not run_script(script):
            print("\n[MASTER] Critical failure in extraction stage. Aborting.")
            sys.exit(1)

    # ---------------------------------------------------------
    # Stage 2: Load Data (Imports JSON to ArangoDB)
    # ---------------------------------------------------------
    print("\n" + "="*40)
    print("STAGE 2: DATA LOADING")
    print("="*40)
    
    # load_data.py now dynamically finds all *_nodes.json and *_edges.json
    if not run_script("load_data.py"):
        print("\n[MASTER] Data loading failed. Aborting.")
        sys.exit(1)

    # ---------------------------------------------------------
    # Stage 3: Direct-to-DB Extractors
    # ---------------------------------------------------------
    print("\n" + "="*40)
    print("STAGE 3: DIRECT DB ENRICHMENT")
    print("="*40)
    
    # Authors script requires GitCommit nodes to be in DB first
    direct_scripts = [
        "etl_authors.py"
    ]
    
    for script in direct_scripts:
        if not run_script(script):
            print(f"\n[MASTER] Warning: {script} failed. Continuing...")

    # ---------------------------------------------------------
    # Stage 4: Semantic Layer (Consolidation & Bridging)
    # ---------------------------------------------------------
    print("\n" + "="*40)
    print("STAGE 4: SEMANTIC LAYER")
    print("="*40)
    
    semantic_scripts = [
        "consolidator.py",
        "bridger_bulk.py"
    ]
    
    for script in semantic_scripts:
        run_script(script)

    print("\n" + "="*80)
    print("MASTER ETL COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
