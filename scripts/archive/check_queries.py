#!/usr/bin/env python3
"""
Check saved queries installation
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db
from config import ARANGO_DATABASE

def check_queries():
    db = get_db()
    
    print("="*60)
    print("Checking Saved Queries")
    print("="*60)
    
    if not db.has_collection("_editor_saved_queries"):
        print("\nERROR: _editor_saved_queries collection not found!")
        return False
    
    queries_col = db.collection("_editor_saved_queries")
    all_queries = list(queries_col.all())
    
    print(f"\nTotal queries in DB: {len(all_queries)}")
    
    # Check for queries with current database name
    our_queries = [q for q in all_queries if q.get('databaseName') == ARANGO_DATABASE]
    print(f"Queries for {ARANGO_DATABASE} database: {len(our_queries)}")
    
    if our_queries:
        print("\nFound queries:")
        for q in our_queries:
            print(f"  - {q.get('title', 'NO TITLE')} (DB: {q.get('databaseName', 'N/A')})")
    
    # Check for queries without database name or wrong database name
    other_queries = [q for q in all_queries if q.get('databaseName') != ARANGO_DATABASE]
    if other_queries:
        print(f"\nQueries for OTHER databases: {len(other_queries)}")
        for q in other_queries[:5]:
            print(f"  - {q.get('title', 'NO TITLE')} (DB: {q.get('databaseName', 'N/A')})")
    
    # Show what database we're currently connected to
    print(f"\nCurrent database: {db.name}")
    
    return len(our_queries) > 0

if __name__ == "__main__":
    check_queries()

