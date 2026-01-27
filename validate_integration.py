#!/usr/bin/env python3
"""
Database Integration Validation
Tests improvements against real ArangoDB data
"""

import sys
import time
import json
from datetime import datetime

sys.path.append('src')
from db_utils import get_db
from config import (
    COL_MODULE, COL_PORT, COL_SIGNAL, EDGE_RESOLVED,
    COL_ENTITIES, COL_RELATIONS
)

def get_baseline_stats(db):
    """Get baseline statistics before improvements"""
    stats = {}
    
    # Total entities
    stats['total_entities'] = db.collection(COL_ENTITIES).count()
    
    # Existing bridges
    for col in [COL_MODULE, COL_PORT, COL_SIGNAL]:
        query = f'''
        FOR edge IN {EDGE_RESOLVED}
            FILTER STARTS_WITH(edge._from, "{col}/")
            COLLECT WITH COUNT INTO total
            RETURN total
        '''
        count = list(db.aql.execute(query))[0] if list(db.aql.execute(query)) else 0
        stats[f'{col}_bridges'] = count
    
    # Total RESOLVED_TO edges
    stats['total_resolved_edges'] = db.collection(EDGE_RESOLVED).count()
    
    # Average scores
    query = f'''
    FOR edge IN {EDGE_RESOLVED}
        FILTER edge.score != null
        COLLECT AGGREGATE avg_score = AVG(edge.score)
        RETURN avg_score
    '''
    result = list(db.aql.execute(query))
    stats['avg_score'] = result[0] if result else 0.0
    
    return stats

def test_fuzzy_consolidation(db):
    """Test fuzzy consolidation dry-run"""
    print("\n=== Testing Fuzzy Consolidation ===")
    
    from consolidator import consolidate_fuzzy_stage2
    
    start_time = time.time()
    candidates = consolidate_fuzzy_stage2(
        db=db,
        levenshtein_distance=1,
        min_confidence=0.75,
        dry_run=True
    )
    elapsed = time.time() - start_time
    
    print(f"✓ Found {len(candidates)} fuzzy match candidates")
    print(f"✓ Query completed in {elapsed:.2f}s")
    
    # Show top candidates
    print("\nTop 10 candidates:")
    for i, cand in enumerate(candidates[:10], 1):
        print(f"{i}. {cand['entity1_name']} ↔ {cand['entity2_name']}")
        print(f"   Confidence: {cand['confidence']:.2f}, Levenshtein: {cand['levenshtein_distance']}")
    
    return {
        'candidate_count': len(candidates),
        'execution_time': elapsed,
        'top_confidence': candidates[0]['confidence'] if candidates else 0.0
    }

def test_graph_aware_context(db):
    """Test graph-aware context retrieval"""
    print("\n=== Testing Graph-Aware Context ===")
    
    from bridger import get_parent_module_context, get_related_entities
    
    # Test with a real port
    test_port = {
        '_key': 'or1200_except.esr',
        'label': 'esr'
    }
    
    print(f"Testing with port: {test_port['_key']}")
    
    start_time = time.time()
    parent_entities = get_parent_module_context(db, test_port, COL_PORT)
    elapsed = time.time() - start_time
    
    print(f"✓ Found {len(parent_entities)} parent module entities")
    print(f"✓ Query completed in {elapsed*1000:.0f}ms")
    
    if parent_entities:
        print(f"  Parent entities: {parent_entities[:3]}")
        
        # Test related entities traversal
        start_time = time.time()
        related = get_related_entities(db, parent_entities)
        elapsed = time.time() - start_time
        
        print(f"✓ Found {len(related)} related entities (depth 1-2)")
        print(f"✓ Traversal completed in {elapsed*1000:.0f}ms")
    
    return {
        'parent_entity_count': len(parent_entities),
        'related_entity_count': len(related) if parent_entities else 0,
        'has_context': len(parent_entities) > 0
    }

def test_index_verification(db):
    """Verify indexes exist"""
    print("\n=== Verifying Indexes ===")
    
    # Check Golden_Entities indexes
    col = db.collection(COL_ENTITIES)
    indexes = col.indexes()
    
    index_names = [idx['name'] for idx in indexes]
    print(f"✓ {COL_ENTITIES} has {len(indexes)} indexes")
    
    # Check for expected indexes
    expected = ['entity_type-index', 'entity_name-index']
    for exp in expected:
        if exp in index_names:
            print(f"  ✓ {exp} exists")
        else:
            print(f"  ⚠ {exp} missing")
    
    # Check RESOLVED_TO collection (edge indexes are automatic)
    if db.has_collection(EDGE_RESOLVED):
        resolved_col = db.collection(EDGE_RESOLVED)
        resolved_indexes = resolved_col.indexes()
        print(f"✓ {EDGE_RESOLVED} has {len(resolved_indexes)} indexes (automatic edge indexes)")
    
    return {
        'golden_entities_indexes': len(indexes),
        'resolved_to_indexes': len(resolved_indexes) if db.has_collection(EDGE_RESOLVED) else 0
    }

def analyze_bridge_coverage(db):
    """Analyze current bridge coverage"""
    print("\n=== Analyzing Bridge Coverage ===")
    
    coverage = {}
    
    for col in [COL_MODULE, COL_PORT, COL_SIGNAL]:
        # Total items
        total = db.collection(col).count()
        
        # Bridged items
        query = f'''
        FOR edge IN {EDGE_RESOLVED}
            FILTER STARTS_WITH(edge._from, "{col}/")
            COLLECT WITH COUNT INTO bridged
            RETURN bridged
        '''
        bridged = list(db.aql.execute(query))[0] if list(db.aql.execute(query)) else 0
        
        percentage = (bridged / total * 100) if total > 0 else 0
        
        coverage[col] = {
            'total': total,
            'bridged': bridged,
            'percentage': percentage
        }
        
        print(f"{col}:")
        print(f"  Total: {total}")
        print(f"  Bridged: {bridged}")
        print(f"  Coverage: {percentage:.1f}%")
    
    return coverage

def test_bulk_bridging_query(db):
    """Test a sample bulk bridging query"""
    print("\n=== Testing Bulk Bridging Query (Sample) ===")
    
    # Test with 5 ports
    query = f'''
    FOR item IN {COL_PORT}
        LIMIT 5
        
        LET norm_label = LOWER(TRIM(item.label))
        FILTER LENGTH(norm_label) >= 2
        
        // Simple candidate search (simplified for testing)
        LET candidates = (
            FOR cand IN {COL_ENTITIES}
                FILTER LOWER(cand.entity_name) == norm_label
                LIMIT 1
                RETURN {{
                    entity_id: cand._id,
                    entity_name: cand.entity_name,
                    score: 0.95
                }}
        )
        
        FILTER LENGTH(candidates) > 0
        
        RETURN {{
            port: item._id,
            match: candidates[0].entity_id,
            score: candidates[0].score
        }}
    '''
    
    start_time = time.time()
    results = list(db.aql.execute(query))
    elapsed = time.time() - start_time
    
    print(f"✓ Processed 5 ports in {elapsed*1000:.0f}ms")
    print(f"✓ Found {len(results)} exact matches")
    
    return {
        'sample_size': 5,
        'matches': len(results),
        'execution_time_ms': elapsed * 1000
    }

def main():
    print("="*60)
    print("Database Integration Validation")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    db = get_db()
    
    # Baseline stats
    print("\n=== Baseline Statistics ===")
    baseline = get_baseline_stats(db)
    for key, value in baseline.items():
        print(f"{key}: {value}")
    
    # Run tests
    results = {
        'timestamp': datetime.now().isoformat(),
        'baseline': baseline
    }
    
    try:
        results['fuzzy_consolidation'] = test_fuzzy_consolidation(db)
    except Exception as e:
        print(f"❌ Fuzzy consolidation test failed: {e}")
        results['fuzzy_consolidation'] = {'error': str(e)}
    
    try:
        results['graph_aware_context'] = test_graph_aware_context(db)
    except Exception as e:
        print(f"❌ Graph-aware context test failed: {e}")
        results['graph_aware_context'] = {'error': str(e)}
    
    try:
        results['indexes'] = test_index_verification(db)
    except Exception as e:
        print(f"❌ Index verification failed: {e}")
        results['indexes'] = {'error': str(e)}
    
    try:
        results['coverage'] = analyze_bridge_coverage(db)
    except Exception as e:
        print(f"❌ Coverage analysis failed: {e}")
        results['coverage'] = {'error': str(e)}
    
    try:
        results['bulk_query_test'] = test_bulk_bridging_query(db)
    except Exception as e:
        print(f"❌ Bulk query test failed: {e}")
        results['bulk_query_test'] = {'error': str(e)}
    
    # Save results
    output_file = 'validation_results_integration.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "="*60)
    print("Validation Complete!")
    print("="*60)
    print(f"Results saved to: {output_file}")
    
    # Summary
    print("\n=== Summary ===")
    if 'fuzzy_consolidation' in results and 'candidate_count' in results['fuzzy_consolidation']:
        print(f"✓ Fuzzy Consolidation: {results['fuzzy_consolidation']['candidate_count']} candidates")
    if 'graph_aware_context' in results and 'has_context' in results['graph_aware_context']:
        status = "✓" if results['graph_aware_context']['has_context'] else "⚠"
        print(f"{status} Graph-Aware Context: {results['graph_aware_context'].get('parent_entity_count', 0)} parent entities")
    if 'coverage' in results:
        for col, data in results['coverage'].items():
            print(f"✓ {col}: {data['percentage']:.1f}% coverage ({data['bridged']}/{data['total']})")

if __name__ == '__main__':
    main()
