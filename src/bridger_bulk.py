"""
AQL Bulk Bridging Implementation
=================================

This is a high-performance alternative to bridger.py that moves the entire
bridging logic into AQL queries. Expected speedup: 10x-100x for large collections.

Key Differences from bridger.py:
1. All similarity computation done in AQL (approximated Jaro-Winkler)
2. Bulk edge generation in single query per collection
3. Graph-aware context integrated into AQL
4. Reduced Python overhead (no ThreadPoolExecutor needed)

Usage:
    python src/bridger_bulk.py              # Bridge all collections
    python src/bridger_bulk.py --modules    # Bridge only modules
    python src/bridger_bulk.py --ports      # Bridge only ports
    python src/bridger_bulk.py --signals    # Bridge only signals
"""

import os
import sys
import time
import logging

# Add src to path to import config
sys.path.append(os.path.join(os.getcwd(), "src"))
from config import (
    COL_MODULE, COL_PORT, COL_SIGNAL, COL_LOGIC,
    COL_CHUNKS, COL_ENTITIES, EDGE_RESOLVED, EDGE_REFERENCES,
    COL_RELATIONS, COL_FSM, COL_PARAMETER, COL_MEMORY,
    COL_CLOCK, COL_BUS
)
from db_utils import get_db

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Type Compatibility Matrix (same as bridger.py)
TYPE_COMPATIBILITY = {
    COL_MODULE: ['processor_component', 'architecture_feature', 'memory_unit', 'hardware_interface', 'configuration', 'UNKNOWN', None],
    COL_PORT: ['register', 'signal', 'hardware_interface', 'architecture_feature', 'UNKNOWN', None],
    COL_SIGNAL: ['register', 'signal', 'architecture_feature', 'UNKNOWN', None],
    COL_LOGIC: ['instruction', 'architecture_feature', 'configuration', 'exception_type', 'UNKNOWN', None],
    COL_BUS: ['hardware_interface', 'bus_protocol', 'architecture_feature', 'processor_component', 'UNKNOWN', None],
    COL_CLOCK: ['architecture_feature', 'clock_domain', 'processor_component', 'UNKNOWN', None],
    COL_FSM: ['architecture_feature', 'state_machine', 'processor_component', 'UNKNOWN', None],
    COL_PARAMETER: ['configuration', 'UNKNOWN', None],
    COL_MEMORY: ['memory_unit', 'processor_component', 'UNKNOWN', None]
}


def create_search_view(db):
    """Create or update ArangoSearch view for bridging"""
    view_name = "harmonized_search_view"
    
    # Check if view exists
    existing_views = [v['name'] for v in db.views()]
    
    properties = {
        "links": {
            COL_MODULE: {
                "fields": {
                    "label": {"analyzers": ["text_en", "identity"]},
                    "metadata": {"fields": {"summary": {"analyzers": ["text_en"]}}}
                }
            },
            COL_PORT: {
                "fields": {
                    "label": {"analyzers": ["text_en", "identity"]},
                    "metadata": {"fields": {"description": {"analyzers": ["text_en"]}}}
                }
            },
            COL_SIGNAL: {
                "fields": {
                    "label": {"analyzers": ["text_en", "identity"]},
                    "metadata": {"fields": {"description": {"analyzers": ["text_en"]}}}
                }
            },
            COL_LOGIC: {"fields": {"label": {"analyzers": ["text_en", "identity"]}, "metadata": {"fields": {"code": {"analyzers": ["text_en"]}}}}},
            COL_BUS: {"fields": {"name": {"analyzers": ["text_en", "identity"]}, "interface_type": {"analyzers": ["text_en", "identity"]}}},
            COL_CLOCK: {"fields": {"name": {"analyzers": ["text_en", "identity"]}}},
            COL_FSM: {"fields": {"name": {"analyzers": ["text_en", "identity"]}}},
            COL_PARAMETER: {"fields": {"name": {"analyzers": ["text_en", "identity"]}}},
            COL_MEMORY: {"fields": {"name": {"analyzers": ["text_en", "identity"]}}},
            COL_ENTITIES: {
            "fields": {
                "label": {"analyzers": ["text_en", "identity"]},
                "entity_name": {"analyzers": ["text_en", "identity"]},
                "description": {"analyzers": ["text_en"]}
            }
        },
            COL_CHUNKS: {"fields": {"content": {"analyzers": ["text_en"]}}}
        }
    }

    if view_name in existing_views:
        logger.info(f"Updating ArangoSearch View '{view_name}'...")
        db.update_view(name=view_name, properties=properties)
        return view_name

    logger.info(f"Creating ArangoSearch View '{view_name}'...")
    db.create_view(
        name=view_name,
        view_type="arangosearch",
        properties=properties
    )
    return view_name


def normalize_name_aql(name_var):
    """
    Returns AQL expression to normalize a hardware name.
    """
    return "LOWER(TRIM(SUBSTITUTE(SUBSTITUTE(" + name_var + ", '_', ' '), REGEX_REPLACE(" + name_var + ", '\\\\s+', ' ', true), ' ')))"


def approximate_jaro_winkler_aql(str1_var, str2_var):
    """
    Returns AQL expression for approximate Jaro-Winkler similarity.
    """
    return "(1.0 - (LEVENSHTEIN_DISTANCE(" + str1_var + ", " + str2_var + ") / MAX([LENGTH(" + str1_var + "), LENGTH(" + str2_var + "), 1])))"


def bulk_bridge_collection(db, col_name, view_name, threshold, method, truncate=False):
    """
    Bulk bridge a collection to Golden Entities using pure AQL.
    
    This function generates RESOLVED_TO edges for all items in a collection
    in a single AQL query, including:
    - Name normalization
    - Type compatibility filtering
    - Similarity scoring (approximate Jaro-Winkler)
    - Graph-aware context boosting (for ports/signals)
    - Best match selection
    
    Args:
        db: ArangoDB connection
        col_name: Source collection name (e.g., COL_MODULE, COL_PORT)
        view_name: ArangoSearch view name
        threshold: Minimum similarity score (0.0-1.0)
        method: Method name for edge metadata
        truncate: If True, truncate RESOLVED_TO before inserting
    """
    logger.info(f"Bulk bridging {col_name} to {COL_ENTITIES}...")
    
    # Get compatible types for this collection
    compatible_types = TYPE_COMPATIBILITY.get(col_name, [])
    
    # Determine label field based on collection
    label_field = "name" if col_name in [COL_BUS, COL_CLOCK, COL_FSM, COL_PARAMETER, COL_MEMORY] else "label"
    
    # Build graph-aware context subquery for ports/signals
    graph_context_clause = ""
    graph_boost_clause = "LET graph_boost = 1.0"
    
    if col_name in [COL_PORT, COL_SIGNAL]:
        # For ports/signals, look up parent module's resolved entities
        graph_context_clause = f"""
        // Extract module name from key (e.g., "or1200_except.esr" -> "or1200_except")
        LET module_name = SPLIT(item._key, ".")[0]
        LET module_id = CONCAT("{COL_MODULE}/", module_name)
        
        // Get parent module's resolved entities
        LET parent_entities = (
            FOR edge IN {EDGE_RESOLVED}
                FILTER edge._from == module_id
                RETURN edge._to
        )
        
        // Get related entities (depth 1-2 traversal)
        LET related_entities = LENGTH(parent_entities) > 0 ? (
            FOR parent_id IN parent_entities
                FOR v, e, p IN 1..2 ANY parent_id {COL_RELATIONS}
                    RETURN DISTINCT v._id
        ) : []
        """
        
        graph_boost_clause = """
        // Apply graph-aware boost if candidate is in related entities
        LET graph_boost = LENGTH(related_entities) > 0 AND cand._id IN related_entities 
            ? 1.20  // 20% boost for entities in parent's neighborhood
            : (LENGTH(related_entities) > 0 ? 0.95 : 1.0)  // Small penalty if we have context but candidate isn't in it
        """
    
    # Main bulk bridging query construction
    norm_item_aql = normalize_name_aql("item_label")
    norm_cand_aql = normalize_name_aql("cand.entity_name")
    similarity_aql = approximate_jaro_winkler_aql("norm_label", "norm_cand_name")

    query = (
        "FOR item IN " + col_name + "\n"
        "    // Extract and normalize item label\n"
        "    LET item_label = item." + label_field + "\n"
        "    FILTER item_label != null AND LENGTH(item_label) >= 2\n\n"
        "    LET norm_label = " + norm_item_aql + "\n\n"
        "    // Graph-aware context (for ports/signals)\n"
        "    " + graph_context_clause + "\n\n"
        "    // Search for candidate entities using ArangoSearch\n"
        "    LET candidates = (\n"
        "        FOR cand IN " + view_name + "\n"
        "            SEARCH (\n"
        "                ANALYZER(cand.entity_name == norm_label, 'identity') OR\n"
        "                ANALYZER(cand.entity_name LIKE CONCAT('%', norm_label, '%'), 'identity') OR\n"
        "                PHRASE(cand.entity_name, norm_label, 'text_en') OR\n"
        "                PHRASE(cand.description, norm_label, 'text_en')\n"
        "            )\n"
        "            FILTER IS_SAME_COLLECTION(@entities_col, cand)\n"
        "            FILTER cand.entity_type IN @compatible_types\n"
        "            SORT BM25(cand) DESC\n"
        "            LIMIT 10\n\n"
        "            LET norm_cand_name = " + norm_cand_aql + "\n\n"
        "            // Approximate Jaro-Winkler similarity using Levenshtein\n"
        "            LET base_score = " + similarity_aql + "\n\n"
        "            // Lexical boost for exact or substring matches\n"
        "            LET is_exact_match = norm_label == norm_cand_name\n"
        "            LET is_substring = CONTAINS(norm_cand_name, norm_label) OR CONTAINS(norm_label, norm_cand_name)\n\n"
        "            LET lexical_boost = is_exact_match ? 0.95 : (is_substring ? 0.80 : base_score)\n"
        "            LET score_with_lexical = MAX([base_score, lexical_boost])\n\n"
        "            // Graph-aware boost (for ports/signals with parent context)\n"
        "            " + graph_boost_clause + "\n\n"
        "            LET final_score = score_with_lexical * graph_boost\n\n"
        "            FILTER final_score > @threshold\n\n"
        "            RETURN {\n"
        "                entity_id: cand._id,\n"
        "                entity_name: cand.entity_name,\n"
        "                score: final_score,\n"
        "                graph_aware: graph_boost > 1.0\n"
        "            }\n"
        "    )\n\n"
        "    // Select best match\n"
        "    LET best_match = LENGTH(candidates) > 0 ? FIRST(\n"
        "        FOR c IN candidates\n"
        "            SORT c.score DESC\n"
        "            LIMIT 1\n"
        "            RETURN c\n"
        "    ) : null\n\n"
        "    FILTER best_match != null\n\n"
        "    RETURN {\n"
        "        _from: item._id,\n"
        "        _to: best_match.entity_id,\n"
        "        score: best_match.score,\n"
        "        method: @method,\n"
        "        graph_aware: best_match.graph_aware\n"
        "    }\n"
    )
    
    bind_vars = {
        "entities_col": COL_ENTITIES,
        "compatible_types": compatible_types,
        "threshold": threshold,
        "method": method
    }
    
    # Execute bulk query
    start_time = time.time()
    logger.info(f"  Executing bulk AQL query...")
    
    try:
        edges = list(db.aql.execute(query, bind_vars=bind_vars))
        query_time = time.time() - start_time
        logger.info(f"  ✓ Query completed in {query_time:.2f}s, generated {len(edges)} edges")
        
        if len(edges) > 0:
            # Insert edges
            if not db.has_collection(EDGE_RESOLVED):
                db.create_collection(EDGE_RESOLVED, edge=True)
            
            if truncate:
                logger.info(f"  Truncating {EDGE_RESOLVED}...")
                db.collection(EDGE_RESOLVED).truncate()
            
            logger.info(f"  Inserting {len(edges)} edges...")
            db.collection(EDGE_RESOLVED).import_bulk(edges)
            
            # Count graph-aware edges
            graph_aware_count = sum(1 for e in edges if e.get('graph_aware', False))
            if graph_aware_count > 0:
                logger.info(f"  ✓ {graph_aware_count} edges used graph-aware context boost")
        
        total_time = time.time() - start_time
        logger.info(f"Completed {col_name} bridging in {total_time:.2f}s")
        
        return len(edges)
        
    except Exception as e:
        logger.error(f"Error during bulk bridging: {e}")
        raise


def bridge_all():
    """Bridge all collections using bulk AQL approach"""
    db = get_db()
    view_name = create_search_view(db)
    
    start_time = time.time()
    total_edges = 0
    
    # Stage 1: Architectural Bridging (Truncate first)
    logger.info("\n=== Stage 1: Architectural Bridging ===")
    total_edges += bulk_bridge_collection(db, COL_BUS, view_name, 0.5, "bulk_arch_bus", truncate=True)
    total_edges += bulk_bridge_collection(db, COL_CLOCK, view_name, 0.5, "bulk_arch_clock")
    total_edges += bulk_bridge_collection(db, COL_FSM, view_name, 0.5, "bulk_arch_fsm")
    total_edges += bulk_bridge_collection(db, COL_PARAMETER, view_name, 0.5, "bulk_arch_param")
    total_edges += bulk_bridge_collection(db, COL_MEMORY, view_name, 0.5, "bulk_arch_mem")
    
    # Stage 2: Structural Bridging (Append)
    logger.info("\n=== Stage 2: Structural Bridging ===")
    total_edges += bulk_bridge_collection(db, COL_MODULE, view_name, 0.7, "bulk_module_v1")
    
    # Stage 3: Granular Bridging (Append) - With Graph-Aware Context
    logger.info("\n=== Stage 3: Granular Bridging (Graph-Aware) ===")
    total_edges += bulk_bridge_collection(db, COL_PORT, view_name, 0.6, "bulk_port_graph_v1")
    total_edges += bulk_bridge_collection(db, COL_SIGNAL, view_name, 0.6, "bulk_signal_graph_v1")
    
    end_time = time.time()
    logger.info(f"\n{'='*60}")
    logger.info(f"Bulk Bridging Complete!")
    logger.info(f"Total edges created: {total_edges}")
    logger.info(f"Total time: {end_time - start_time:.2f}s")
    logger.info(f"{'='*60}")


def bridge_modules_only():
    """Bridge only modules"""
    db = get_db()
    view_name = create_search_view(db)
    bulk_bridge_collection(db, COL_MODULE, view_name, 0.7, "bulk_module_v1", truncate=True)


def bridge_ports_only():
    """Bridge only ports"""
    db = get_db()
    view_name = create_search_view(db)
    bulk_bridge_collection(db, COL_PORT, view_name, 0.6, "bulk_port_graph_v1")


def bridge_signals_only():
    """Bridge only signals"""
    db = get_db()
    view_name = create_search_view(db)
    bulk_bridge_collection(db, COL_SIGNAL, view_name, 0.6, "bulk_signal_graph_v1")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "--modules":
            bridge_modules_only()
        elif command == "--ports":
            bridge_ports_only()
        elif command == "--signals":
            bridge_signals_only()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python bridger_bulk.py [--modules|--ports|--signals]")
            sys.exit(1)
    else:
        bridge_all()
