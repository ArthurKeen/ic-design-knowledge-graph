#!/usr/bin/env python3
"""
Fix canvas actions by linking them to the correct viewpoint
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db

def fix_canvas_actions():
    db = get_db()
    
    print("="*60)
    print("Fixing Canvas Actions Links")
    print("="*60)
    
    # Find the OR1200 viewpoint
    viewpoints_col = db.collection('_viewpoints')
    viewpoints = list(viewpoints_col.all())
    
    or1200_viewpoint = None
    for vp in viewpoints:
        # Check if this is the OR1200 graph viewpoint
        # It might have graphName or we need to check its linked graph
        print(f"\nChecking viewpoint: {vp['_id']}")
        print(f"  Keys: {list(vp.keys())}")
        
        # This is likely the OR1200 viewpoint since there's only one
        if len(viewpoints) == 1 or 'OR1200' in str(vp):
            or1200_viewpoint = vp
            print(f"  -> Using this as OR1200 viewpoint")
            break
    
    if not or1200_viewpoint:
        print("\nERROR: Could not find OR1200 viewpoint!")
        return False
    
    viewpoint_id = or1200_viewpoint['_id']
    print(f"\nTarget viewpoint: {viewpoint_id}")
    
    # Get our canvas actions
    actions_col = db.collection('_canvasActions')
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
    
    # Create or update links
    links_col = db.collection('_viewpointActions')
    linked_count = 0
    
    for action_key in our_action_keys:
        if not actions_col.has(action_key):
            print(f"\n  [SKIP] Action not found: {action_key}")
            continue
        
        action_id = f"_canvasActions/{action_key}"
        
        # Check if link already exists
        existing = list(links_col.find({'_from': viewpoint_id, '_to': action_id}))
        
        if existing:
            print(f"\n  [EXISTS] {action_key}")
        else:
            # Create new link FROM viewpoint TO action
            edge = {
                '_from': viewpoint_id,
                '_to': action_id
            }
            links_col.insert(edge)
            print(f"\n  [CREATED] {action_key}")
            linked_count += 1
    
    print(f"\n{'='*60}")
    print(f"Linked {linked_count} new actions")
    print(f"{'='*60}")
    
    # Verify
    print("\nVerifying links...")
    all_links = list(links_col.find({'_from': viewpoint_id}))
    print(f"Total links from {viewpoint_id}: {len(all_links)}")
    for link in all_links[:5]:
        print(f"  - {link['_to']}")
    if len(all_links) > 5:
        print(f"  ... and {len(all_links) - 5} more")
    
    return True

if __name__ == "__main__":
    success = fix_canvas_actions()
    sys.exit(0 if success else 1)

