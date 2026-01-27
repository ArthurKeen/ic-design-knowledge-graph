#!/usr/bin/env python3
"""
Check and fix canvas actions setup
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db

def check_viewpoints():
    db = get_db()
    
    print("="*60)
    print("Checking Viewpoint Structure")
    print("="*60)
    
    # Check _viewpoints collection (this might be the key)
    if db.has_collection('_viewpoints'):
        print("\n_viewpoints collection exists!")
        viewpoints = list(db.collection('_viewpoints').all())
        print(f"Documents: {len(viewpoints)}")
        for vp in viewpoints:
            print(f"\n  {vp['_id']}:")
            print(f"    graphName: {vp.get('graphName', 'N/A')}")
            print(f"    databaseName: {vp.get('databaseName', 'N/A')}")
            if 'OR1200' in str(vp):
                print(f"    MATCH! This viewpoint is for OR1200_Knowledge_Graph")
    else:
        print("\n_viewpoints collection does NOT exist")
    
    # Check our installed actions
    print("\n" + "="*60)
    print("Checking our installed actions")
    print("="*60)
    
    if db.has_collection('_canvasActions'):
        actions = db.collection('_canvasActions')
        
        # Look for actions with our specific keys
        our_actions = [
            'show_entity_resolutions',
            'show_module_internals',
            'find_implementing_code'
        ]
        
        for key in our_actions:
            if actions.has(key):
                action = actions.get(key)
                print(f"\n  Found: {key}")
                print(f"    _id: {action['_id']}")
                print(f"    title: {action.get('title', 'MISSING')}")
                print(f"    query preview: {action.get('query', 'N/A')[:50]}...")
            else:
                print(f"\n  NOT FOUND: {key}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    check_viewpoints()

