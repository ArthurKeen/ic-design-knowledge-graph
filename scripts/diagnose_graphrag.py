#!/usr/bin/env python3
"""
GraphRAG Import Diagnostic Tool

Provides detailed feedback on the PDF→Markdown→Import process
"""

import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import (
    SERVER_URL, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE,
    OR1200_DOCS, GRAPHRAG_ENTITY_TYPES, GRAPHRAG_CHUNK_TOKEN_SIZE,
    GRAPHRAG_ENABLE_CHUNK_EMBEDDINGS, GRAPHRAG_PREFIX
)
from graphrag_client import GraphRAGClient
from document_converter import DocumentConverter
from db_utils import get_db

def check_collections(db):
    """Check current state of collections"""
    collections = {}
    suffixes = ['Chunks', 'Entities', 'Golden_Entities', 'Relations', 
                'Golden_Relations', 'Communities', 'Documents']
    
    for suffix in suffixes:
        col_name = f"{GRAPHRAG_PREFIX}{suffix}"
        if db.has_collection(col_name):
            count = db.collection(col_name).count()
            collections[col_name] = count
        else:
            collections[col_name] = None
    
    return collections

def main():
    print("=" * 80)
    print("GraphRAG Import Diagnostic Tool")
    print("=" * 80)
    
    # Configuration check
    print("\n1. Configuration Check:")
    print(f"   Server: {SERVER_URL}")
    print(f"   Database: {ARANGO_DATABASE}")
    print(f"   Documents to process: {len(OR1200_DOCS)}")
    print(f"   Entity types: {len(GRAPHRAG_ENTITY_TYPES)}")
    print(f"   Chunk size: {GRAPHRAG_CHUNK_TOKEN_SIZE}")
    
    # Check service ID
    if len(sys.argv) < 2:
        print("\nError: No importer service ID provided")
        print("Usage: python diagnose_graphrag.py <importer_service_id>")
        print("Example: python diagnose_graphrag.py 0hjss")
        sys.exit(1)
    
    importer_id = sys.argv[1]
    print(f"   Importer Service ID: {importer_id}")
    
    # Authenticate
    print("\n2. Authenticating...")
    client = GraphRAGClient(SERVER_URL, ARANGO_USERNAME, ARANGO_PASSWORD)
    if client.authenticate():
        print("   ✓ Authentication successful")
    else:
        print("   ✗ Authentication failed")
        sys.exit(1)
    
    # Check database connection
    print("\n3. Checking database connection...")
    try:
        db = get_db()
        print(f"   ✓ Connected to database: {db.name}")
    except Exception as e:
        print(f"   ✗ Database connection failed: {e}")
        sys.exit(1)
    
    # Check initial collection state
    print("\n4. Initial collection state:")
    initial_counts = check_collections(db)
    for col_name, count in initial_counts.items():
        if count is None:
            print(f"   - {col_name}: NOT FOUND")
        else:
            print(f"   - {col_name}: {count} docs")
    
    # Convert PDFs to Markdown
    print("\n5. Converting PDFs to Markdown (UTF-8)...")
    markdown_dir = Path("markdown_output")
    markdown_dir.mkdir(exist_ok=True)
    
    converter = DocumentConverter(method='pymupdf')
    markdown_files = []
    
    for i, pdf_path in enumerate(OR1200_DOCS, 1):
        if not os.path.exists(pdf_path):
            print(f"   [{i}/{len(OR1200_DOCS)}] ✗ PDF not found: {pdf_path}")
            continue
        
        filename = os.path.basename(pdf_path)
        md_filename = filename.replace('.pdf', '.md')
        md_path = markdown_dir / md_filename
        
        print(f"   [{i}/{len(OR1200_DOCS)}] Converting {filename}...", end=" ")
        try:
            md_content = converter.convert(pdf_path, str(md_path))
            markdown_files.append(str(md_path))
            
            # Verify file was written
            file_size = os.path.getsize(md_path)
            print(f"✓ {len(md_content):,} chars, {file_size:,} bytes on disk")
            
            # Check encoding
            with open(md_path, 'rb') as f:
                first_bytes = f.read(3)
                has_bom = (first_bytes == b'\xef\xbb\xbf')
                print(f"      UTF-8 BOM: {'Yes' if has_bom else 'No (clean UTF-8)'}")
                
        except Exception as e:
            print(f"✗ Error: {e}")
            continue
    
    print(f"\n   ✓ Converted {len(markdown_files)}/{len(OR1200_DOCS)} documents")
    
    if not markdown_files:
        print("\n✗ No markdown files to import. Exiting.")
        sys.exit(1)
    
    # Import documents
    print("\n6. Importing Markdown files to GraphRAG...")
    print(f"   Using importer service: {importer_id}")
    print()
    
    successful = []
    failed = []
    
    for i, md_path in enumerate(markdown_files, 1):
        filename = os.path.basename(md_path)
        print(f"   [{i}/{len(markdown_files)}] Importing {filename}...")
        
        try:
            # Import with detailed response
            response = client.import_document(
                service_id=importer_id,
                file_path=md_path,
                partition_id=f"or1200_{i}",
                entity_types=GRAPHRAG_ENTITY_TYPES,
                chunk_size=GRAPHRAG_CHUNK_TOKEN_SIZE,
                enable_embeddings=GRAPHRAG_ENABLE_CHUNK_EMBEDDINGS
            )
            
            # Analyze response
            print(f"      Response: {json.dumps(response, indent=8)}")
            
            success = response.get('success', False)
            message = response.get('message', 'No message')
            
            if success:
                print(f"      ✓ {message}")
                successful.append(filename)
            else:
                print(f"      ✗ {message}")
                failed.append(filename)
                
        except Exception as e:
            print(f"      ✗ Exception: {e}")
            failed.append(filename)
    
    print(f"\n   Import Results: {len(successful)} successful, {len(failed)} failed")
    
    # Monitor collections for 5 minutes
    print("\n7. Monitoring collections (checking every 30 seconds for 5 minutes)...")
    
    for check in range(10):  # 10 checks x 30 seconds = 5 minutes
        time.sleep(30)
        
        current_counts = check_collections(db)
        changes = {}
        
        for col_name, count in current_counts.items():
            if count is not None and initial_counts.get(col_name) is not None:
                delta = count - initial_counts[col_name]
                if delta > 0:
                    changes[col_name] = (initial_counts[col_name], count, delta)
        
        timestamp = time.strftime('%H:%M:%S')
        print(f"\n   [{timestamp}] Check {check + 1}/10:")
        
        if changes:
            print("      Collections with new data:")
            for col_name, (old, new, delta) in changes.items():
                print(f"        ✓ {col_name}: {old} → {new} (+{delta})")
        else:
            total = sum(c for c in current_counts.values() if c)
            print(f"      No changes yet (total docs: {total})")
        
        # If we see significant data, we're done
        total_new = sum(delta for _, _, delta in changes.values())
        if total_new > 100:
            print(f"\n   ✓ Significant data loaded ({total_new} new documents)!")
            break
    
    # Final summary
    print("\n" + "=" * 80)
    print("Final Summary:")
    print("=" * 80)
    
    final_counts = check_collections(db)
    for col_name, count in final_counts.items():
        if count is not None:
            initial = initial_counts.get(col_name, 0) or 0
            delta = count - initial
            if delta > 0:
                print(f"  ✓ {col_name}: {count} docs (+{delta})")
            else:
                print(f"  - {col_name}: {count} docs (no change)")
        else:
            print(f"  - {col_name}: NOT FOUND")
    
    total_added = sum(
        (final_counts.get(k, 0) or 0) - (initial_counts.get(k, 0) or 0)
        for k in final_counts
    )
    
    if total_added > 0:
        print(f"\n✓ SUCCESS: {total_added} new documents added to collections")
    else:
        print(f"\n✗ NO DATA: Collections unchanged after import")
        print("\nPossible issues:")
        print("  1. Import service may be processing in background (wait longer)")
        print("  2. File encoding issue (check UTF-8)")
        print("  3. Service configuration problem")
        print("  4. Check service logs for errors")

if __name__ == '__main__':
    main()
