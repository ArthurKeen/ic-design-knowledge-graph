#!/usr/bin/env python3
"""
Check and fix canvas action names
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db

def check_and_fix_names():
    db = get_db()
    
    print("="*60)
    print("Checking Canvas Action Names")
    print("="*60)
    
    actions_col = db.collection("_canvasActions")
    
    # Get our actions
    our_action_keys = [
        'show_entity_resolutions',
        'show_module_internals',
        'find_implementing_code',
        'show_containment_tree',
        'show_docs_for_modified_modules',
        'expand_entity_relationships',
        'show_wiring_connections',
        'find_parent_module',
        'show_commit_history',
        'full_neighborhood'
    ]
    
    print("\nChecking fields in our actions:")
    for key in our_action_keys[:3]:  # Check first 3
        if actions_col.has(key):
            action = actions_col.get(key)
            print(f"\n{key}:")
            print(f"  Fields: {list(action.keys())}")
            print(f"  title: {action.get('title', 'MISSING')}")
            print(f"  name: {action.get('name', 'MISSING')}")
            print(f"  description: {action.get('description', 'MISSING')[:50]}...")
    
    # The UI might be looking for 'name' field instead of 'title'
    # Let's add 'name' field to all our actions
    print("\n" + "="*60)
    print("Adding 'name' field to actions...")
    print("="*60)
    
    fixed = 0
    for key in our_action_keys:
        if actions_col.has(key):
            action = actions_col.get(key)
            
            # If name is missing but title exists, copy title to name
            if 'title' in action and 'name' not in action:
                action['name'] = action['title']
                # Use replace to ensure the field is added
                actions_col.replace({'_key': key}, action)
                print(f"  Fixed: {action['title']}")
                fixed += 1
            elif 'name' in action:
                print(f"  Already has name: {action['name']}")
    
    print(f"\n{'='*60}")
    print(f"Fixed {fixed} actions")
    print(f"{'='*60}")
    print("\nPlease refresh your browser to see the changes.")

if __name__ == "__main__":
    check_and_fix_names()

