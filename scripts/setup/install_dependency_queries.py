#!/usr/bin/env python3
"""
Module Dependency Analysis - Graph Visualizer Setup

This script installs saved queries and canvas actions for analyzing
module dependencies in the OR1200 hardware design.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from db_utils import get_db, get_system_db
import json

def install_dependency_queries(db):
    """Install saved queries for module dependency analysis"""
    
    sys_db = get_system_db()
    
    # Ensure collection exists
    if not sys_db.has_collection('_editor_saved_queries'):
        try:
             sys_db.create_collection('_editor_saved_queries')
        except: pass
        
    queries_col = sys_db.collection('_editor_saved_queries')
    
    queries = [
        {
            "name": "Module Dependency Graph",
            "queryText": """
// Show all module dependencies
FOR v, e, p IN 1..10 OUTBOUND 'RTL_Module/or1200_cpu' GRAPH 'IC_Knowledge_Graph'
  FILTER e.type == 'DEPENDS_ON'
  RETURN p
""",
            "description": "Visualize the complete dependency tree starting from the CPU module"
        },
        {
            "name": "Direct Dependencies of Module",
            "queryText": """
// What modules does this one depend on directly?
FOR v IN 1..1 OUTBOUND @module DEPENDS_ON
  RETURN {
    module: v._key,
    name: v.name,
    summary: v.summary,
    instance_count: LENGTH(FOR e IN DEPENDS_ON FILTER e._from == @module && e._to == v._id RETURN e)[0].instance_count
  }
""",
            "description": "Find all modules that a given module depends on (1-hop)",
            "bindVariables": {"module": "RTL_Module/or1200_alu"}
        },
        {
            "name": "Reverse Dependencies (Who Uses This)",
            "queryText": """
// Which modules depend on this module?
FOR v IN 1..1 INBOUND @module DEPENDS_ON
  RETURN {
    module: v._key,
    name: v.name,
    summary: v.summary,
    instance_count: LENGTH(FOR e IN DEPENDS_ON FILTER e._to == @module && e._from == v._id RETURN e)[0].instance_count
  }
""",
            "description": "Find all modules that depend on a given module (reverse dependencies)",
            "bindVariables": {"module": "RTL_Module/or1200_alu"}
        },
        {
            "name": "Full Dependency Chain",
            "queryText": """
// Complete dependency chain from top to bottom
FOR v, e, p IN 1..10 OUTBOUND @start_module DEPENDS_ON
  OPTIONS {uniqueVertices: "path"}
  RETURN p
""",
            "description": "Trace the full dependency chain from a module to all its transitive dependencies",
            "bindVariables": {"start_module": "RTL_Module/or1200_cpu"}
        },
        {
            "name": "Circular Dependency Check",
            "queryText": """
// Check for circular dependencies (should be none in good design)
FOR v IN RTL_Module
  LET paths = (
    FOR v2, e, p IN 2..10 OUTBOUND v DEPENDS_ON
      FILTER v2._id == v._id
      RETURN p
  )
  FILTER LENGTH(paths) > 0
  RETURN {
    module: v._key,
    circular_paths: paths
  }
""",
            "description": "Detect circular dependencies in the module hierarchy"
        },
        {
            "name": "Dependency Depth Analysis",
            "queryText": """
// How deep is the dependency tree for each module?
FOR v IN RTL_Module
  LET max_depth = MAX(
    FOR v2, e, p IN 1..10 OUTBOUND v DEPENDS_ON
      RETURN LENGTH(p.edges)
  )
  RETURN {
    module: v._key,
    name: v.name,
    max_dependency_depth: max_depth || 0,
    is_leaf: max_depth == null
  }
  SORT max_dependency_depth DESC
""",
            "description": "Calculate the maximum dependency depth for each module"
        },
        {
            "name": "Most Reused Modules",
            "queryText": """
// Which modules are instantiated most frequently?
FOR v IN RTL_Module
  LET dependents = (
    FOR e IN DEPENDS_ON
      FILTER e._to == v._id
      RETURN {
        from: e._from,
        instance_count: e.instance_count
      }
  )
  LET total_instances = SUM(dependents[*].instance_count)
  LET unique_parents = LENGTH(UNIQUE(dependents[*].from))
  FILTER unique_parents > 0
  RETURN {
    module: v._key,
    name: v.name,
    used_by_modules: unique_parents,
    total_instances: total_instances,
    dependents: dependents
  }
  SORT used_by_modules DESC, total_instances DESC
  LIMIT 20
""",
            "description": "Find the most heavily reused modules across the design"
        },
        {
            "name": "Leaf Modules (No Dependencies)",
            "queryText": """
// Find modules that don't depend on anything (primitives/leaves)
FOR v IN RTL_Module
  LET deps = (
    FOR v2 IN 1..1 OUTBOUND v DEPENDS_ON
      RETURN 1
  )
  FILTER LENGTH(deps) == 0
  RETURN {
    module: v._key,
    name: v.name,
    summary: v.summary
  }
""",
            "description": "List all leaf modules that have no dependencies"
        },
        {
            "name": "Top-Level Modules (Nothing Depends on Them)",
            "queryText": """
// Find modules that nothing else depends on (top-level)
FOR v IN RTL_Module
  LET reverse_deps = (
    FOR v2 IN 1..1 INBOUND v DEPENDS_ON
      RETURN 1
  )
  FILTER LENGTH(reverse_deps) == 0
  RETURN {
    module: v._key,
    name: v.name,
    summary: v.summary
  }
""",
            "description": "List all top-level modules (entry points)"
        },
        {
            "name": "Module Impact Analysis",
            "queryText": """
// If I change this module, what else is affected?
FOR v, e, p IN 1..10 INBOUND @module DEPENDS_ON
  OPTIONS {uniqueVertices: "path"}
  RETURN {
    affected_module: v._key,
    depth: LENGTH(p.edges),
    path: p.vertices[*]._key
  }
  SORT depth ASC
""",
            "description": "Show all modules that would be impacted by changes to a given module",
            "bindVariables": {"module": "RTL_Module/or1200_alu"}
        }
    ]
    
    print("\n[1/2] Installing Dependency Analysis Queries...")
    installed = 0
    updated = 0
    
    for query in queries:
        # Check if query already exists
        existing = list(queries_col.find({"name": query["name"]}))
        
        if existing:
            queries_col.update({"_key": existing[0]["_key"]}, query)
            print(f"  Updated: {query['name']}")
            updated += 1
        else:
            queries_col.insert(query)
            print(f"  Installed: {query['name']}")
            installed += 1
    
    print(f"  Total queries processed: {len(queries)} (installed: {installed}, updated: {updated})")
    return True

def install_dependency_actions(db):
    """Install canvas actions for interactive dependency exploration"""
    
    sys_db = get_system_db()
    
    if not sys_db.has_collection('_canvasActions'):
        try:
            sys_db.create_collection('_canvasActions')
        except: pass
        
    actions_col = sys_db.collection('_canvasActions')
    
    actions = [
        {
            "name": "Show Module Dependencies",
            "title": "Show Module Dependencies",
            "queryText": """
FOR v IN 1..1 OUTBOUND @nodes[0] DEPENDS_ON
  RETURN v
""",
            "graphId": "IC_Knowledge_Graph",
            "bindVariables": {"nodes": []}
        },
        {
            "name": "Show Modules That Depend on This",
            "title": "Show Modules That Depend on This",
            "queryText": """
FOR v IN 1..1 INBOUND @nodes[0] DEPENDS_ON
  RETURN v
""",
            "graphId": "IC_Knowledge_Graph",
            "bindVariables": {"nodes": []}
        },
        {
            "name": "Show Full Dependency Tree",
            "title": "Show Full Dependency Tree",
            "queryText": """
FOR v, e, p IN 1..5 OUTBOUND @nodes[0] DEPENDS_ON
  RETURN p
""",
            "graphId": "IC_Knowledge_Graph",
            "bindVariables": {"nodes": []}
        },
        {
            "name": "Show Impact Chain",
            "title": "Show Impact Chain (Reverse)",
            "queryText": """
FOR v, e, p IN 1..5 INBOUND @nodes[0] DEPENDS_ON
  RETURN p
""",
            "graphId": "IC_Knowledge_Graph",
            "bindVariables": {"nodes": []}
        }
    ]
    
    print("\n[2/2] Installing Dependency Canvas Actions...")
    installed = 0
    updated = 0
    
    for action in actions:
        # Check if action already exists
        existing = list(actions_col.find({"name": action["name"]}))
        
        if existing:
            actions_col.update({"_key": existing[0]["_key"]}, action)
            print(f"  Updated: {action['name']}")
            updated += 1
        else:
            result = actions_col.insert(action)
            print(f"  Installed: {action['name']}")
            installed += 1
            
            # Link to viewpoint
            viewpoints_col = db.collection('_viewpoints')
            viewpoint_actions_col = db.collection('_viewpointActions')
            
            # Find the viewpoint for our graph
            viewpoints = list(viewpoints_col.find({"graphId": "IC_Knowledge_Graph"}))
            if viewpoints:
                viewpoint_id = viewpoints[0]['_id']
                action_id = result['_id']
                
                # Create edge from viewpoint to action
                edge = {
                    "_from": viewpoint_id,
                    "_to": action_id
                }
                viewpoint_actions_col.insert(edge)
    
    print(f"  Total actions processed: {len(actions)} (installed: {installed}, updated: {updated})")
    return True

def main():
    """Main installation routine"""
    print("="*60)
    print("Module Dependency Analysis - Query & Action Installer")
    print("="*60)
    
    # Connect to database
    print("\nConnecting to database...")
    try:
        db = get_db()
        print(f"Connected to: {db.name}")
    except Exception as e:
        print(f"\nError connecting to database: {e}")
        print("Make sure your .env file is configured correctly.")
        sys.exit(1)
    
    # Verify graph exists
    if not db.has_graph("IC_Knowledge_Graph"):
        print("\nWarning: Graph 'IC_Knowledge_Graph' not found.")
        print("Run the ETL pipeline first to create the graph.")
        sys.exit(1)
    
    # Install queries and actions
    try:
        install_dependency_queries(db)
        install_dependency_actions(db)
        
        print("\n" + "="*60)
        print("Installation Complete!")
        print("="*60)
        print("\nNew Features Available:")
        print("  - 10 saved queries for dependency analysis")
        print("  - 4 canvas actions for interactive exploration")
        print("\nUsage:")
        print("  1. Open ArangoDB web interface")
        print("  2. Navigate to: Graphs → IC_Knowledge_Graph")
        print("  3. Click 'Queries' to run saved queries")
        print("  4. Right-click any module → Canvas Action for interactive exploration")
        print("="*60 + "\n")
        
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Installation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

