#!/usr/bin/env python3
"""
Clean reinstall of canvas actions with proper name fields
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db

def reinstall_actions():
    db = get_db()
    
    print("="*60)
    print("Clean Reinstall of Canvas Actions")
    print("="*60)
    
    actions_col = db.collection("_canvasActions")
    
    # Our actions with proper structure
    actions = [
        {
            '_key': 'show_entity_resolutions',
            'name': 'Show Entity Resolutions',
            'title': 'Show Entity Resolutions',
            'description': 'Display specification entities linked to selected RTL nodes',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..1 OUTBOUND node\n    GRAPH "OR1200_Knowledge_Graph"\n    FILTER IS_SAME_COLLECTION("OR1200_Golden_Entities", v)\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'show_module_internals',
            'name': 'Show Module Internals',
            'title': 'Show Module Internals',
            'description': 'Display ports and signals for selected modules',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..1 OUTBOUND node\n    GRAPH "OR1200_Knowledge_Graph"\n    FILTER e.type IN ["HAS_PORT", "HAS_SIGNAL"]\n    LIMIT 30\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'find_implementing_code',
            'name': 'Find Implementing Code',
            'title': 'Find Implementing Code',
            'description': 'Reverse search from specification entity to RTL code',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..1 INBOUND node\n    GRAPH "OR1200_Knowledge_Graph"\n    FILTER e.type == "RESOLVED_TO"\n    FILTER IS_SAME_COLLECTION("RTL_Signal", v) \n       OR IS_SAME_COLLECTION("RTL_Port", v)\n       OR IS_SAME_COLLECTION("RTL_Module", v)\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'show_containment_tree',
            'name': 'Show Containment Tree',
            'title': 'Show Containment Tree',
            'description': 'Expand selected module to show sub-modules and logic',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..2 OUTBOUND node\n    GRAPH "OR1200_Knowledge_Graph"\n    FILTER e.type == "CONTAINS"\n    LIMIT 40\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'show_docs_for_modified_modules',
            'name': 'Show Documentation for Modified Modules',
            'title': 'Show Documentation for Modified Modules',
            'description': 'From a commit, show affected specification entities',
            'queryText': 'FOR commitNode IN @nodes\n  FOR module, modEdge IN 1..1 OUTBOUND commitNode\n    GRAPH "OR1200_Knowledge_Graph"\n    FILTER modEdge.type == "MODIFIED"\n    FOR entity, resEdge, path IN 1..1 OUTBOUND module\n      GRAPH "OR1200_Knowledge_Graph"\n      FILTER resEdge.type == "RESOLVED_TO"\n      RETURN path',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'expand_entity_relationships',
            'name': 'Expand Entity Relationships',
            'title': 'Expand Entity Relationships',
            'description': 'Show related documentation entities via GraphRAG relations',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..1 ANY node\n    OR1200_Golden_Relations\n    FILTER IS_SAME_COLLECTION("OR1200_Golden_Entities", v)\n    LIMIT 20\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'show_wiring_connections',
            'name': 'Show Wiring Connections',
            'title': 'Show Wiring Connections',
            'description': 'Display structural wiring from selected ports',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..1 ANY node\n    GRAPH "OR1200_Knowledge_Graph"\n    FILTER e.type == "WIRED_TO"\n    LIMIT 20\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'find_parent_module',
            'name': 'Find Parent Module',
            'title': 'Find Parent Module',
            'description': 'Navigate up the hierarchy from a component',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..1 INBOUND node\n    GRAPH "OR1200_Knowledge_Graph"\n    FILTER e.type == "CONTAINS" OR e.type == "HAS_PORT" OR e.type == "HAS_SIGNAL"\n    FILTER IS_SAME_COLLECTION("RTL_Module", v)\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'show_commit_history',
            'name': 'Show Commit History',
            'title': 'Show Commit History',
            'description': 'Show commits that modified selected modules',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..1 INBOUND node\n    GRAPH "OR1200_Knowledge_Graph"\n    FILTER e.type == "MODIFIED"\n    FILTER IS_SAME_COLLECTION("GitCommit", v)\n    SORT v.timestamp DESC\n    LIMIT 10\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        },
        {
            '_key': 'full_neighborhood',
            'name': 'Full Neighborhood (2-hop)',
            'title': 'Full Neighborhood (2-hop)',
            'description': 'General exploration - show everything connected within 2 hops',
            'queryText': 'FOR node IN @nodes\n  FOR v, e, p IN 1..2 ANY node\n    GRAPH "OR1200_Knowledge_Graph"\n    LIMIT 50\n    RETURN p',
            'graphId': 'OR1200_Knowledge_Graph',
            'bindVariables': {'nodes': []},
            'createdAt': '2026-01-02T12:00:00.000Z'
        }
    ]
    
    print("\nDeleting old actions...")
    deleted = 0
    for action in actions:
        key = action['_key']
        try:
            actions_col.delete(key)
            print(f"  Deleted: {key}")
            deleted += 1
        except:
            print(f"  Not found: {key}")
    
    print(f"\nDeleted {deleted} actions")
    
    print("\nInserting fresh actions...")
    inserted = 0
    for action in actions:
        try:
            actions_col.insert(action)
            print(f"  Inserted: {action['name']}")
            inserted += 1
        except Exception as e:
            print(f"  Error inserting {action['_key']}: {e}")
    
    print(f"\n{'='*60}")
    print(f"Reinstalled {inserted} actions")
    print(f"{'='*60}")
    
    # Verify one
    print("\nVerifying first action...")
    test = actions_col.get('show_entity_resolutions')
    print(f"  name: {test.get('name', 'MISSING')}")
    print(f"  title: {test.get('title', 'MISSING')}")
    print(f"  graphId: {test.get('graphId', 'MISSING')}")
    print(f"  queryText: {test.get('queryText', 'MISSING')[:30]}...")
    print(f"  bindVariables: {test.get('bindVariables', 'MISSING')}")
    
    print("\nNow run: python scripts/archive/fix_canvas_actions.py")
    print("to relink them to the viewpoint.")

if __name__ == "__main__":
    reinstall_actions()

