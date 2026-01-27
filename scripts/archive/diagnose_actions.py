#!/usr/bin/env python3
"""
Diagnostic script to check canvas actions installation
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db

def diagnose():
    db = get_db()
    
    print("="*60)
    print("Canvas Actions Diagnostic")
    print("="*60)
    
    # Check if collections exist
    print("\n1. Collections Check:")
    print(f"   _canvasActions exists: {db.has_collection('_canvasActions')}")
    print(f"   _viewpointActions exists: {db.has_collection('_viewpointActions')}")
    
    # Count actions
    if db.has_collection('_canvasActions'):
        actions = list(db.collection('_canvasActions').all())
        print(f"\n2. Canvas Actions in DB: {len(actions)}")
        for action in actions[:5]:  # Show first 5
            print(f"   - {action.get('title', 'N/A')} ({action['_id']})")
        if len(actions) > 5:
            print(f"   ... and {len(actions) - 5} more")
    
    # Check links
    if db.has_collection('_viewpointActions'):
        links = list(db.collection('_viewpointActions').all())
        print(f"\n3. Action Links (_viewpointActions): {len(links)}")
        for link in links[:5]:  # Show first 5
            print(f"   - {link['_from']} -> {link['_to']}")
        if len(links) > 5:
            print(f"   ... and {len(links) - 5} more")
    
    # Check for existing viewpoint structure
    print(f"\n4. _viewpointGraph exists: {db.has_collection('_viewpointGraph')}")
    if db.has_collection('_viewpointGraph'):
        vp_graph = list(db.collection('_viewpointGraph').all())
        print(f"   Documents in _viewpointGraph: {len(vp_graph)}")
        for doc in vp_graph:
            print(f"   - {doc['_id']}: {doc.get('name', 'N/A')}")
    
    # Check what graphs exist
    print(f"\n5. Named Graphs:")
    graphs = db.graphs()
    for graph in graphs:
        print(f"   - {graph['name']}")
    
    # Try to find the correct target for links
    print(f"\n6. Checking for graph representation in collections:")
    if db.has_collection('_graphs'):
        graph_docs = list(db.collection('_graphs').find({'name': 'OR1200_Knowledge_Graph'}))
        if graph_docs:
            print(f"   Found in _graphs collection:")
            for doc in graph_docs:
                print(f"   - {doc['_id']}")
        else:
            print(f"   No document found in _graphs for OR1200_Knowledge_Graph")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    diagnose()

