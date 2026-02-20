#!/usr/bin/env python3
"""
Install Hardware Design Theme for Graph Visualizer
==========================================

This script installs the 'hardware-design' theme into the _graphThemeStore collection.

Usage:
    python install_theme.py
"""

import os
import sys
import json
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from db_utils import get_db
except ImportError:
    print("Error: Could not import db_utils. Make sure you're in the project root.")
    sys.exit(1)


def install_theme(db):
    """Install the hardware-design theme into _graphThemeStore collection."""
    print("\nInstalling OR1200 Theme...")
    print("="*60)
    
    # Load theme from JSON file in docs/
    theme_file = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'hardware_design_theme.json')
    
    if not os.path.exists(theme_file):
        print(f"\nError: Theme file not found: {theme_file}")
        sys.exit(1)
    
    with open(theme_file, 'r') as f:
        theme = json.load(f)
    
    # Add timestamps
    now = datetime.utcnow().isoformat() + "Z"
    theme["createdAt"] = now
    theme["updatedAt"] = now
    
    # Ensure collection exists in current database
    if not db.has_collection("_graphThemeStore"):
        print("  [PREREQ] Collection _graphThemeStore not found in this database.")
        print("  ArangoDB creates Visualizer metadata collections when you open the graph in the UI.")
        print("  Action: Open Graph Visualizer for this DB (Graphs → IC_Knowledge_Graph) once, then rerun this script.")
        return False
            
    theme_col = db.collection("_graphThemeStore")
    
    # Check if theme already exists
    existing = list(theme_col.find({
        "graphId": theme["graphId"],
        "name": theme["name"]
    }))
    
    if existing:
        # Update existing theme
        doc_key = existing[0]["_key"]
        theme["updatedAt"] = now
        theme_col.update({"_key": doc_key}, theme)
        print(f"\n  [SUCCESS] Updated existing theme: '{theme['name']}'")
        print(f"  Theme ID: {existing[0]['_id']}")
    else:
        # Insert new theme
        result = theme_col.insert(theme)
        print(f"\n  [SUCCESS] Installed new theme: '{theme['name']}'")
        print(f"  Theme ID: {result['_id']}")
    
    # Display theme details
    print(f"\n  Graph: {theme['graphId']}")
    print(f"  Description: {theme['description']}")
    print(f"\n  Node Collections Configured: {len(theme['nodeConfigMap'])}")
    for coll in sorted(theme['nodeConfigMap'].keys()):
        config = theme['nodeConfigMap'][coll]
        color = config['background']['color']
        icon = config['background']['iconName']
        print(f"    - {coll}: {color} ({icon})")
    
    print(f"\n  Edge Collections Configured: {len(theme['edgeConfigMap'])}")
    for coll in sorted(theme['edgeConfigMap'].keys()):
        config = theme['edgeConfigMap'][coll]
        color = config['lineStyle']['color']
        thickness = config['lineStyle']['thickness']
        print(f"    - {coll}: {color} (thickness: {thickness})")
    
    return True


def verify_theme(db):
    """Verify the theme was installed correctly."""
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
        
    if not db.has_collection("_graphThemeStore"):
        print("\n  [FAIL] Collection _graphThemeStore not found in current database")
        return False
    
    theme_col = db.collection("_graphThemeStore")
    
    # Check for hardware-design theme
    hardware_themes = list(theme_col.find({"name": "hardware-design"}))
    
    if not hardware_themes:
        print("\n  [FAIL] Theme 'hardware-design' not found")
        return False
    
    print(f"\n  [PASS] Theme 'hardware-design' found")
    print(f"  Total themes in store: {theme_col.count()}")
    
    # List all themes
    all_themes = list(theme_col.all())
    print(f"\n  Available themes:")
    for theme in all_themes:
        is_default = " (default)" if theme.get("isDefault") else ""
        is_current = " <- CURRENT" if theme["name"] == "hardware-design" else ""
        print(f"    - {theme['name']}{is_default}{is_current}")
    
    print("\n" + "="*60)
    print("Installation successful!")
    print("\nNext steps:")
    print("1. Open ArangoDB web interface")
    print("2. Navigate to: Graphs → IC_Knowledge_Graph")
    print("3. Click 'Legend' button (top right)")
    print("4. Click theme dropdown at top of Legend panel")
    print("5. Select 'hardware-design' theme")
    print("6. Canvas will update with new colors and icons")
    print("="*60 + "\n")
    
    return True


def main():
    """Main installation routine."""
    print("="*60)
    print("OR1200 Theme Installer")
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
        print("The theme will still be installed, but won't be visible until the graph exists.")
    
    # Install theme
    try:
        installed = install_theme(db)
        success = verify_theme(db) if installed else False
        # Non-zero exit indicates the UI prerequisite has not been met yet.
        sys.exit(0 if success else 2)
    except Exception as e:
        print(f"\n[ERROR] Installation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

