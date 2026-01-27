#!/usr/bin/env python3
"""
Compare our actions with the working one to see what's different
"""
import os
import sys
import json
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db

def compare_actions():
    db = get_db()
    
    print("="*60)
    print("Comparing Actions")
    print("="*60)
    
    actions_col = db.collection("_canvasActions")
    
    # Find the action that HAS a name showing
    all_actions = list(actions_col.all())
    
    print(f"\nTotal actions in DB: {len(all_actions)}")
    
    # Look for actions with different structures
    print("\nActions with 'name' field:")
    for action in all_actions:
        if 'name' in action:
            print(f"\n  {action['_key']}:")
            print(f"    name: {action['name']}")
            print(f"    Fields: {sorted(action.keys())}")
            break
    
    print("\nOur action (show_entity_resolutions):")
    if actions_col.has('show_entity_resolutions'):
        our_action = actions_col.get('show_entity_resolutions')
        print(f"    Fields: {sorted(our_action.keys())}")
        print(f"    name: {our_action.get('name', 'MISSING')}")
        print(f"    title: {our_action.get('title', 'MISSING')}")
        print(f"\n    Full document:")
        print(json.dumps(our_action, indent=2, default=str))

if __name__ == "__main__":
    compare_actions()

