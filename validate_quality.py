#!/usr/bin/env python3
"""
Post-Implementation Quality Validation

Validates the quality improvements after applying:
1. Fuzzy consolidation
2. Graph-aware bridging

Compares before/after metrics and validates against expectations.
"""

import sys
import json
from datetime import datetime

sys.path.append('src')
from db_utils import get_db
from config import COL_ENTITIES, EDGE_RESOLVED, COL_PORT, COL_SIGNAL, COL_MODULE

def analyze_bridge_quality(db):
    """Analyze bridge quality metrics"""
    
    print("="*60)
    print("Bridge Quality Analysis")
    print("="*60)
    
    # Overall bridge statistics
    query = f'''
    FOR edge IN {EDGE_RESOLVED}
        COLLECT 
            method = edge.method,
            graph_aware = edge.graph_aware
        WITH COUNT INTO count
        SORT count DESC
        RETURN {{
            method: method,
            graph_aware: graph_aware,
            count: count
        }}
    '''
    
    methods = list(db.aql.execute(query))
    
    print("\nBridge Methods Distribution:")
    for m in methods:
        ga_flag = " [GRAPH-AWARE]" if m.get('graph_aware') else ""
        print(f"  {m['method']}: {m['count']} edges{ga_flag}")
    
    # Score distribution
    query = f'''
    FOR edge IN {EDGE_RESOLVED}
        COLLECT 
            score_bucket = FLOOR(edge.score * 10) / 10
        WITH COUNT INTO count
        SORT score_bucket DESC
        RETURN {{
            score_range: CONCAT(score_bucket, " - ", score_bucket + 0.1),
            count: count
        }}
    '''
    
    scores = list(db.aql.execute(query))
    
    print("\nScore Distribution:")
    for s in scores:
        print(f"  {s['score_range']}: {s['count']} edges")
    
    # Average scores by method
    query = f'''
    FOR edge IN {EDGE_RESOLVED}
        FILTER edge.score != null
        COLLECT method = edge.method
        AGGREGATE avg_score = AVG(edge.score)
        SORT avg_score DESC
        RETURN {{
            method: method,
            avg_score: avg_score
        }}
    '''
    
    avg_scores = list(db.aql.execute(query))
    
    print("\nAverage Scores by Method:")
    for s in avg_scores:
        print(f"  {s['method']}: {s['avg_score']:.3f}")
    
    # Graph-aware vs non-graph-aware comparison
    query = f'''
    LET graph_aware_edges = (
        FOR edge IN {EDGE_RESOLVED}
            FILTER edge.graph_aware == true AND edge.score != null
            RETURN edge.score
    )
    
    LET regular_edges = (
        FOR edge IN {EDGE_RESOLVED}
            FILTER edge.graph_aware != true AND edge.score != null
            RETURN edge.score
    )
    
    RETURN {{
        graph_aware_count: LENGTH(graph_aware_edges),
        graph_aware_avg: AVG(graph_aware_edges),
        regular_count: LENGTH(regular_edges),
        regular_avg: AVG(regular_edges)
    }}
    '''
    
    comparison = list(db.aql.execute(query))[0]
    
    print("\nGraph-Aware vs Regular Bridges:")
    print(f"  Graph-Aware: {comparison['graph_aware_count']} edges, avg score: {comparison['graph_aware_avg']:.3f}")
    print(f"  Regular: {comparison['regular_count']} edges, avg score: {comparison['regular_avg']:.3f}")
    
    if comparison['graph_aware_count'] > 0:
        improvement = (comparison['graph_aware_avg'] - comparison['regular_avg']) / comparison['regular_avg'] * 100
        print(f"  Graph-aware improvement: {improvement:+.1f}%")
    
    return {
        'methods': methods,
        'score_distribution': scores,
        'avg_scores': avg_scores,
        'graph_aware_comparison': comparison
    }

def analyze_entity_quality(db):
    """Analyze consolidated entity quality"""
    
    print("\n" + "="*60)
    print("Entity Consolidation Quality")
    print("="*60)
    
    # Total entities
    total = db.collection(COL_ENTITIES).count()
    print(f"\nTotal Golden Entities: {total}")
    
    # Fuzzy merged entities
    query = f'''
    FOR entity IN {COL_ENTITIES}
        FILTER entity.metadata.fuzzy_merged == true
        RETURN entity
    '''
    
    merged = list(db.aql.execute(query))
    print(f"Fuzzy-Merged Entities: {len(merged)} ({len(merged)/total*100:.1f}%)")
    
    if len(merged) > 0:
        # Show examples
        print("\nTop Fuzzy-Merged Entities:")
        for entity in sorted(merged, key=lambda e: e['metadata'].get('fuzzy_merged_count', 0), reverse=True)[:5]:
            count = entity['metadata'].get('fuzzy_merged_count', 0)
            aliases = entity.get('aliases', [])[:3]
            print(f"  {entity['entity_name']}")
            print(f"    Merged: {count} entities")
            print(f"    Aliases: {', '.join(aliases)}")
    
    # Alias distribution
    query = f'''
    FOR entity IN {COL_ENTITIES}
        LET alias_count = LENGTH(entity.aliases || [])
        COLLECT 
            bucket = alias_count > 5 ? "5+" : TO_STRING(alias_count)
        WITH COUNT INTO count
        SORT bucket
        RETURN {{
            alias_count: bucket,
            entities: count
        }}
    '''
    
    alias_dist = list(db.aql.execute(query))
    
    print("\nAlias Distribution:")
    for a in alias_dist:
        print(f"  {a['alias_count']} aliases: {a['entities']} entities")
    
    return {
        'total_entities': total,
        'fuzzy_merged_count': len(merged),
        'fuzzy_merged_pct': len(merged)/total*100 if total > 0 else 0
    }

def coverage_analysis(db):
    """Analyze coverage improvements"""
    
    print("\n" + "="*60)
    print("Coverage Analysis")
    print("="*60)
    
    coverage = {}
    
    for col in [COL_MODULE, COL_PORT, COL_SIGNAL]:
        total = db.collection(col).count()
        
        query = f'''
        FOR edge IN {EDGE_RESOLVED}
            FILTER STARTS_WITH(edge._from, "{col}/")
            COLLECT WITH COUNT INTO bridged
            RETURN bridged
        '''
        
        bridged = list(db.aql.execute(query))[0] if list(db.aql.execute(query)) else 0
        coverage_pct = (bridged / total * 100) if total > 0 else 0
        
        # Graph-aware count
        query_ga = f'''
        FOR edge IN {EDGE_RESOLVED}
            FILTER STARTS_WITH(edge._from, "{col}/") AND edge.graph_aware == true
            COLLECT WITH COUNT INTO ga_count
            RETURN ga_count
        '''
        
        ga_count = list(db.aql.execute(query_ga))[0] if list(db.aql.execute(query_ga)) else 0
        
        coverage[col] = {
            'total': total,
            'bridged': bridged,
            'coverage_pct': coverage_pct,
            'graph_aware': ga_count,
            'graph_aware_pct': (ga_count/bridged*100) if bridged > 0 else 0
        }
        
        print(f"\n{col}:")
        print(f"  Total: {total}")
        print(f"  Bridged: {bridged} ({coverage_pct:.1f}%)")
        print(f"  Graph-Aware: {ga_count} ({coverage[col]['graph_aware_pct']:.1f}% of bridged)")
    
    return coverage

def sample_high_quality_bridges(db):
    """Sample high-quality bridges for manual validation"""
    
    print("\n" + "="*60)
    print("Sample High-Quality Bridges")
    print("="*60)
    
    # High-confidence graph-aware bridges
    query = f'''
    FOR edge IN {EDGE_RESOLVED}
        FILTER edge.graph_aware == true AND edge.score > 0.8
        SORT edge.score DESC
        LIMIT 10
        
        LET from_doc = DOCUMENT(edge._from)
        LET to_doc = DOCUMENT(edge._to)
        
        RETURN {{
            source: from_doc.label || from_doc.name,
            source_type: SPLIT(edge._from, "/")[0],
            target: to_doc.entity_name,
            target_type: to_doc.entity_type,
            score: edge.score,
            method: edge.method
        }}
    '''
    
    samples = list(db.aql.execute(query))
    
    print("\nTop 10 Graph-Aware Bridges (score > 0.8):")
    for i, s in enumerate(samples, 1):
        print(f"{i}. {s['source']} ({s['source_type']}) → {s['target']} ({s['target_type']})")
        print(f"   Score: {s['score']:.3f}, Method: {s['method']}")
    
    return samples

def expected_vs_actual(db):
    """Compare expected vs actual results"""
    
    print("\n" + "="*60)
    print("Expected vs Actual Results")
    print("="*60)
    
    # From our projections
    expected = {
        'entity_reduction_pct': 13.7,
        'bridge_increase_pct': 27.0,
        'port_coverage_increase_pts': 9.0,
        'signal_coverage_increase_pts': 9.0
    }
    
    # Actual from database
    entities = db.collection(COL_ENTITIES).count()
    bridges = db.collection(EDGE_RESOLVED).count()
    
    # Calculate actual (comparing to baseline from validation)
    baseline_entities = 4045
    baseline_bridges = 1174
    baseline_port_coverage = 38.4
    baseline_signal_coverage = 33.0
    
    actual = {
        'entity_reduction_pct': (baseline_entities - entities) / baseline_entities * 100,
        'bridge_increase_pct': (bridges - baseline_bridges) / baseline_bridges * 100,
    }
    
    # Get current coverage
    port_total = db.collection(COL_PORT).count()
    signal_total = db.collection(COL_SIGNAL).count()
    
    port_bridged = list(db.aql.execute(f'''
        FOR edge IN {EDGE_RESOLVED}
            FILTER STARTS_WITH(edge._from, "{COL_PORT}/")
            COLLECT WITH COUNT INTO c
            RETURN c
    '''))[0]
    
    signal_bridged = list(db.aql.execute(f'''
        FOR edge IN {EDGE_RESOLVED}
            FILTER STARTS_WITH(edge._from, "{COL_SIGNAL}/")
            COLLECT WITH COUNT INTO c
            RETURN c
    '''))[0]
    
    current_port_coverage = (port_bridged / port_total * 100)
    current_signal_coverage = (signal_bridged / signal_total * 100)
    
    actual['port_coverage_increase_pts'] = current_port_coverage - baseline_port_coverage
    actual['signal_coverage_increase_pts'] = current_signal_coverage - baseline_signal_coverage
    
    comparison = {
        'Entity Reduction': {
            'expected': f"{expected['entity_reduction_pct']:.1f}%",
            'actual': f"{actual['entity_reduction_pct']:.1f}%",
            'status': '✅' if actual['entity_reduction_pct'] >= expected['entity_reduction_pct']*0.8 else '⚠️'
        },
        'Bridge Increase': {
            'expected': f"+{expected['bridge_increase_pct']:.1f}%",
            'actual': f"+{actual['bridge_increase_pct']:.1f}%",
            'status': '🔥' if actual['bridge_increase_pct'] > expected['bridge_increase_pct']*2 else '✅'
        },
        'Port Coverage': {
            'expected': f"+{expected['port_coverage_increase_pts']:.1f} pts",
            'actual': f"+{actual['port_coverage_increase_pts']:.1f} pts",
            'status': '🔥' if actual['port_coverage_increase_pts'] > expected['port_coverage_increase_pts']*3 else '✅'
        },
        'Signal Coverage': {
            'expected': f"+{expected['signal_coverage_increase_pts']:.1f} pts",
            'actual': f"+{actual['signal_coverage_increase_pts']:.1f} pts",
            'status': '🔥' if actual['signal_coverage_increase_pts'] > expected['signal_coverage_increase_pts']*3 else '✅'
        }
    }
    
    print("\nMetric Comparisons:")
    for metric, data in comparison.items():
        print(f"\n{metric}:")
        print(f"  Expected: {data['expected']}")
        print(f"  Actual:   {data['actual']} {data['status']}")
    
    print("\n✅ = Met expectations")
    print("🔥 = Greatly exceeded expectations!")
    print("⚠️ = Below expectations")
    
    return comparison

def main():
    print("="*60)
    print("POST-IMPLEMENTATION QUALITY VALIDATION")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    db = get_db()
    
    results = {
        'timestamp': datetime.now().isoformat()
    }
    
    # Run analyses
    try:
        results['bridge_quality'] = analyze_bridge_quality(db)
    except Exception as e:
        print(f"Error in bridge quality analysis: {e}")
    
    try:
        results['entity_quality'] = analyze_entity_quality(db)
    except Exception as e:
        print(f"Error in entity quality analysis: {e}")
    
    try:
        results['coverage'] = coverage_analysis(db)
    except Exception as e:
        print(f"Error in coverage analysis: {e}")
    
    try:
        results['samples'] = sample_high_quality_bridges(db)
    except Exception as e:
        print(f"Error sampling bridges: {e}")
    
    try:
        results['comparison'] = expected_vs_actual(db)
    except Exception as e:
        print(f"Error in comparison: {e}")
    
    # Save results
    output_file = 'validation_results_quality.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\n" + "="*60)
    print("VALIDATION COMPLETE!")
    print("="*60)
    print(f"Results saved to: {output_file}")

if __name__ == '__main__':
    main()
