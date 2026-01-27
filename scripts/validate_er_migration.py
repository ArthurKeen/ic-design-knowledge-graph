#!/usr/bin/env python3
"""
Validation Script for ER Library Migration
Verifies that the arango-entity-resolution library is correctly installed
and can be imported with the new package structure.
"""

import sys

def test_import():
    """Test if the library can be imported with new structure"""
    print("Testing arango-entity-resolution library import...")
    try:
        from arango_er.similarity.weighted_field_similarity import WeightedFieldSimilarity
        print("✓ Import successful: WeightedFieldSimilarity found")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        print("\nTo fix this, run:")
        print("  pip install arango-entity-resolution==3.1.0")
        return False

def test_initialization():
    """Test if the library can be initialized"""
    print("\nTesting WeightedFieldSimilarity initialization...")
    try:
        from arango_er.similarity.weighted_field_similarity import WeightedFieldSimilarity
        
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.7, 'description': 0.3},
            algorithm='jaro_winkler'
        )
        print("✓ Initialization successful")
        print(f"  Algorithm: {similarity.algorithm}")
        print(f"  Field weights: {similarity.field_weights}")
        return True
    except Exception as e:
        print(f"✗ Initialization failed: {e}")
        return False

def test_similarity_computation():
    """Test basic similarity computation"""
    print("\nTesting similarity computation...")
    try:
        from arango_er.similarity.weighted_field_similarity import WeightedFieldSimilarity
        
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.7, 'description': 0.3},
            algorithm='jaro_winkler'
        )
        
        doc1 = {
            "name": "or1200_alu",
            "description": "Arithmetic Logic Unit for OR1200 processor"
        }
        doc2 = {
            "name": "alu",
            "description": "ALU arithmetic logic unit"
        }
        
        score = similarity.compute(doc1, doc2)
        print(f"✓ Similarity computation successful")
        print(f"  Test score: {score:.4f}")
        print(f"  (Higher = more similar, range 0.0-1.0)")
        return True
    except Exception as e:
        print(f"✗ Similarity computation failed: {e}")
        return False

def check_no_legacy_imports():
    """Check that no legacy imports exist in the codebase"""
    print("\nChecking for legacy import patterns...")
    import os
    import re
    
    legacy_patterns = [
        r'from entity_resolution\.',
        r'import entity_resolution',
    ]
    
    issues_found = []
    src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')
    
    for filename in os.listdir(src_dir):
        if filename.endswith('.py'):
            filepath = os.path.join(src_dir, filename)
            with open(filepath, 'r') as f:
                content = f.read()
                for pattern in legacy_patterns:
                    if re.search(pattern, content):
                        issues_found.append(f"  {filename}: legacy import pattern '{pattern}'")
    
    if issues_found:
        print("✗ Legacy imports found:")
        for issue in issues_found:
            print(issue)
        return False
    else:
        print("✓ No legacy import patterns found")
        return True

def main():
    """Run all validation tests"""
    print("=" * 60)
    print("ArangoDB Entity Resolution Library Migration Validation")
    print("=" * 60)
    
    results = []
    
    # Test 1: Import
    results.append(("Import Test", test_import()))
    
    # Test 2: Initialization (only if import worked)
    if results[0][1]:
        results.append(("Initialization Test", test_initialization()))
        
        # Test 3: Computation (only if initialization worked)
        if results[1][1]:
            results.append(("Computation Test", test_similarity_computation()))
    
    # Test 4: Check for legacy imports
    results.append(("Legacy Import Check", check_no_legacy_imports()))
    
    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 Migration validation SUCCESSFUL!")
        print("The arango-entity-resolution library is correctly installed and configured.")
        return 0
    else:
        print("\n⚠️  Migration validation FAILED")
        print("Please review the errors above and install the library:")
        print("  pip install arango-entity-resolution==3.1.0")
        return 1

if __name__ == "__main__":
    sys.exit(main())
