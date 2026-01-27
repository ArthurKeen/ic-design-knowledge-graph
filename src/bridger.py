import os
import sys
import json
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# Add src to path to import config
sys.path.append(os.path.join(os.getcwd(), "src"))
from config import (
    COL_MODULE, COL_PORT, COL_SIGNAL, COL_LOGIC,
    COL_CHUNKS, COL_ENTITIES, EDGE_RESOLVED, EDGE_REFERENCES,
    COL_DOCS, COL_RELATIONS, COL_FSM, COL_PARAMETER, COL_MEMORY,
    COL_CLOCK, COL_BUS
)
from db_utils import get_db
from utils import normalize_hardware_name

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import ER Library components (v3.1.0+)
try:
    from entity_resolution.similarity.weighted_field_similarity import WeightedFieldSimilarity
except ImportError as e:
    print(f"Error: Could not import arango-entity-resolution library. Please install it:")
    print(f"  pip install arango-entity-resolution==3.1.0")
    print(f"")
    print(f"If you have SSL certificate issues, use:")
    print(f"  pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org arango-entity-resolution==3.1.0")
    print(f"")
    print(f"Import error details: {e}")
    sys.exit(1)

# Global similarity instance for threads
# Phase 2 Enhancement: Multi-field similarity with name and description
SIMILARITY = WeightedFieldSimilarity(
    field_weights={'name': 0.7, 'description': 0.3},
    algorithm='jaro_winkler'
)

# Type Compatibility Matrix (Phase 2 Action Plan)
# Maps RTL collection types to sets of compatible Golden Entity types.
TYPE_COMPATIBILITY = {
    COL_MODULE: {'processor_component', 'architecture_feature', 'memory_unit', 'hardware_interface', 'configuration', 'UNKNOWN', None},
    COL_PORT: {'register', 'signal', 'hardware_interface', 'architecture_feature', 'UNKNOWN', None},
    COL_SIGNAL: {'register', 'signal', 'architecture_feature', 'UNKNOWN', None},
    COL_LOGIC: {'instruction', 'architecture_feature', 'configuration', 'exception_type', 'UNKNOWN', None},
    COL_BUS: {'hardware_interface', 'bus_protocol', 'architecture_feature', 'processor_component', 'UNKNOWN', None},
    COL_CLOCK: {'architecture_feature', 'clock_domain', 'processor_component', 'UNKNOWN', None},
    COL_FSM: {'architecture_feature', 'state_machine', 'processor_component', 'UNKNOWN', None},
    COL_PARAMETER: {'configuration', 'UNKNOWN', None},
    COL_MEMORY: {'memory_unit', 'processor_component', 'UNKNOWN', None}
}

def create_search_view(db):
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
        print(f"Updating ArangoSearch View '{view_name}'...")
        db.update_view(name=view_name, properties=properties)
        return view_name

    print(f"Creating ArangoSearch View '{view_name}'...")
    db.create_view(
        name=view_name,
        view_type="arangosearch",
        properties=properties
    )
    return view_name

def get_parent_module_context(db, item, col_name):
    """
    For ports/signals, find the parent module and retrieve its resolved entities.
    Returns a list of entity IDs that the parent module is resolved to.
    
    This enables graph-aware bridging: if module 'or1200_alu' is resolved to 
    'ALU_Unit' entity, then when bridging 'alu_op' signal, we prioritize entities
    that are related to 'ALU_Unit'.
    """
    if col_name not in [COL_PORT, COL_SIGNAL]:
        return []
    
    # Extract module name from item key (e.g., "or1200_except.esr" -> "or1200_except")
    parts = item.get('_key', '').split('.')
    if len(parts) < 2:
        return []
    
    module_name = parts[0]
    module_id = f"{COL_MODULE}/{module_name}"
    
    # Query: Find all Golden Entities that this module resolves to
    query = f"""
    FOR edge IN {EDGE_RESOLVED}
        FILTER edge._from == @module_id
        RETURN edge._to
    """
    
    try:
        resolved_entities = list(db.aql.execute(query, bind_vars={"module_id": module_id}))
        return resolved_entities
    except Exception as e:
        logger.debug(f"Could not fetch parent context for {module_id}: {e}")
        return []


def get_related_entities(db, parent_entity_ids):
    """
    Given a list of parent entity IDs, find entities that are related to them
    via Golden_Relations edges. This includes PART_OF, RELATED_TO, CONTAINS, etc.
    
    Returns a set of entity IDs that are within the same conceptual "neighborhood"
    as the parent entities.
    
    Optimization Note (VCI):
    Currently this traverses Golden_Relations without filtering on entity_type,
    which is correct for our use case (we want all related entities regardless of type).
    
    If we needed to filter by entity_type during traversal, we should use
    Vertex-Centric Indexing (VCI):
    1. Copy entity_type onto Golden_Relations edges as source_type/target_type
    2. Create composite indexes: (_from, source_type), (_to, target_type)
    3. Filter on edge attributes instead of vertex attributes
    
    See docs/reference/optimization.md for details.
    """
    if not parent_entity_ids:
        return set()
    
    # Query: Find entities connected to parent entities (depth 1-2)
    # We look for both outgoing and incoming edges
    # No type filtering needed here - we want all related entities
    query = f"""
    FOR parent_id IN @parent_ids
        FOR v, e, p IN 1..2 ANY parent_id {COL_RELATIONS}
            RETURN DISTINCT v._id
    """
    
    try:
        related = list(db.aql.execute(query, bind_vars={"parent_ids": parent_entity_ids}))
        return set(related + parent_entity_ids)  # Include parents themselves
    except Exception as e:
        logger.debug(f"Could not fetch related entities: {e}")
        return set(parent_entity_ids)


def calculate_token_overlap(text1, text2):
    if not text1 or not text2:
        return 0.0
    # Simple tokenization
    tokens1 = set(re.findall(r'\w+', text1.lower()))
    tokens2 = set(re.findall(r'\w+', text2.lower()))
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'is', 'are', 'of', 'in', 'to', 'for', 'and', 'or', 'be', 'with', 'on', 'at', 'by', 'this', 'that', 'it'}
    tokens1 -= stop_words
    tokens2 -= stop_words
    
    if not tokens1 or not tokens2:
        return 0.0
        
    intersection = tokens1.intersection(tokens2)
    min_len = min(len(tokens1), len(tokens2)) 
    # Overlap Coefficient
    return len(intersection) / min_len if min_len > 0 else 0.0

def process_item_to_entity(db, item, view_name, threshold, method, context_summary="", parent_entity_ids=None):
    label = item.get("label") or item.get("name", "")
    if not label:
        return []
    
    # Extract expanded_name from metadata if available
    metadata = item.get("metadata", {})
    expanded_name = metadata.get("expanded_name", "")
    
    # Extract RTL headers/comments
    rtl_description = metadata.get("summary") or metadata.get("description", "")
    
    # For BusInterface, also include the interface type (e.g., "Wishbone")
    interface_type = item.get("interface_type", "")
    
    search_term = normalize_hardware_name(label)
    if not search_term or len(search_term) < 2:
        return []

    # Build enhanced search term combining label and expanded form
    # e.g., "esr" + "Exception Status Register" -> search for both
    search_terms = [search_term]
    if expanded_name:
        expanded_normalized = normalize_hardware_name(expanded_name)
        if expanded_normalized and expanded_normalized != search_term:
            search_terms.append(expanded_normalized)
            
    if interface_type:
        interface_normalized = normalize_hardware_name(interface_type)
        if interface_normalized and interface_normalized not in search_terms:
            search_terms.append(interface_normalized)
    
    # Join all search terms for query
    combined_search = " ".join(search_terms)
    
    # Use the longest available name for similarity computation (most descriptive)
    best_source_name = max(search_terms, key=len)
    
    # Combined description: original label + any RTL comments/headers
    source_description = label
    parent_label = item.get("parent_label", "")
    if parent_label:
        source_description += f" in {normalize_hardware_name(parent_label)}"
    if rtl_description:
        source_description += f" {rtl_description}"
    
    # Phase 2 Enhancement: Get compatible entity types for source collection
    source_col = item["_id"].split('/')[0]
    compatible_types = list(TYPE_COMPATIBILITY.get(source_col, set()))
    
    # Phase 3 Enhancement: Graph-Aware Context
    # If parent_entity_ids provided, get related entities for prioritization
    related_entities = set()
    if parent_entity_ids:
        related_entities = get_related_entities(db, parent_entity_ids)
        logger.debug(f"Graph-aware context: {len(related_entities)} related entities for {label}")
    
    # Enhanced AQL Query with Context and Type Pre-Filtering
    # If context is provided, we boost results where the description contains terms from the context
    context_clause = ""
    bind_vars ={
        "term": search_term,
        "combined": combined_search,  # Add combined search term
        "fuzzy": f"%{search_term}%",
        "entities_col": COL_ENTITIES,
        "compatible_types": compatible_types  # Phase 2: Add type filter
    }
    
    if context_summary:
        # Extract key terms from context summary (simple approach: use first 5 meaningful words)
        # or just pass the whole summary to ANALYZER
        context_clause = """
            OR (
                ANALYZER(doc.description IN TOKENS(@context, "text_en"), "text_en") 
                OR PHRASE(doc.description, @term, "text_en")
            )
        """
        bind_vars["context"] = context_summary

    # Updated query with type pre-filtering (Phase 2 Enhancement)
    # Use PHRASE for standard search, but also allow flexible token matching for architectural components
    is_architectural = source_col in [COL_BUS, COL_CLOCK, COL_FSM, COL_PARAMETER, COL_MEMORY]
    
    search_clause = f"""
             ANALYZER(doc.entity_name == @term, "identity") OR 
             ANALYZER(doc.entity_name LIKE @fuzzy, "identity") OR
             PHRASE(doc.entity_name, @combined, "text_en") OR
             PHRASE(doc.description, @combined, "text_en")
    """
    
    if is_architectural:
        # For architectural components, also match if most tokens match (e.g., "Wishbone Data" -> "DATA WISHBONE INTERFACE")
        search_clause += """
             OR ANALYZER(doc.entity_name IN TOKENS(@combined, "text_en"), "text_en")
        """

    if rtl_description:
        # Boost matches that appear in the RTL header/inline comments
        search_clause += " OR ANALYZER(doc.entity_name IN TOKENS(@rtl_desc, 'text_en'), 'text_en')"
        bind_vars["rtl_desc"] = rtl_description

    query = f"""
    FOR doc IN {view_name}
      SEARCH (
             {search_clause}
             {context_clause}
      )
      FILTER IS_SAME_COLLECTION(@entities_col, doc)
      FILTER doc.entity_type IN @compatible_types  // Phase 2: Type pre-filtering
      SORT BM25(doc) DESC
      LIMIT 10
      RETURN {{
          _id: doc._id,
          entity_name: doc.entity_name,
          description: doc.description,
          entity_type: doc.entity_type
      }}
    """
    
    
    candidates = list(db.aql.execute(query, bind_vars=bind_vars))

    matches = []
    for cand in candidates:
        cand_name = cand.get("entity_name", "")
        cand_desc = cand.get("description", "")
        n_cand = normalize_hardware_name(cand_name)
        
        # Phase 2 Enhancement: Multi-field similarity
        # Include both name and description in similarity calculation
        doc1 = {
            "name": best_source_name,
            "description": source_description
        }
        doc2 = {
            "name": n_cand,
            "description": cand_desc if cand_desc else n_cand  # Fallback to name if no description
        }
        er_score = SIMILARITY.compute(doc1, doc2)
        
        # Base Score
        final_score = er_score
        
        # Lexical Boost (capped)
        # Check against both normalized original and expanded name
        lexical_match = False
        for s_term in search_terms:
            if s_term == n_cand:
                lexical_match = True
                break
            # Token-based subset check (e.g. "multiplier" in "multiplier unit")
            s_tokens = set(s_term.split())
            c_tokens = set(n_cand.split())
            if s_tokens.issubset(c_tokens) or c_tokens.issubset(s_tokens):
                lexical_match = True
                break
                
        if lexical_match:
            final_score = max(final_score, 0.95 if any(s == n_cand for s in search_terms) else 0.85)
        elif any(s in n_cand or n_cand in s for s in search_terms):
            final_score = max(final_score, 0.80)
            
        # Context Weighting
        if context_summary:
            overlap = calculate_token_overlap(context_summary, cand_desc)
            
            # If we have meaningful context overlap, we blend it
            if overlap > 0.0:
                # 70% Lexical, 30% Context - ensures name match is still primary
                final_score = (final_score * 0.7) + (overlap * 0.3)
            else:
                 # Penalty for context mismatch
                 final_score = final_score * 0.9

        # Phase 3 Enhancement: Graph-Aware Context Boost
        # If candidate is in the related entities set, boost the score
        if related_entities and cand["_id"] in related_entities:
            # Boost by 20% for entities in the parent module's graph neighborhood
            final_score = min(1.0, final_score * 1.20)
            logger.debug(f"Graph boost applied to {cand_name} (in parent's neighborhood)")
        elif related_entities:
            # Small penalty for entities outside the neighborhood (we have context but this isn't in it)
            final_score = final_score * 0.95

        # Phase 2 Note: Type filtering now happens in AQL pre-filter
        # Removed redundant type penalty logic - candidates are already type-compatible

        if final_score > threshold:
            matches.append({
                "_from": item["_id"],
                "_to": cand["_id"],
                "score": final_score,
                "method": method,
                "graph_aware": bool(related_entities and cand["_id"] in related_entities)
            })
            
    # Return only the single best match
    if matches:
        matches.sort(key=lambda x: x['score'], reverse=True)
        return [matches[0]]
        
    return []

def bridge_collection_parallel(db, col_name, view_name, threshold, method, truncate=False):
    print(f"Bridging {col_name} to Entities in parallel...")
    items = list(db.collection(col_name).all())
    print(f"Found {len(items)} items in {col_name}.")

    resolved_edges = []
    
    # Pre-fetch module labels and resolved entities if bridging ports/signals
    module_summaries = {}
    module_labels = {}
    module_resolved_entities = {}  # New: Track which entities each module resolves to
    
    if col_name in [COL_PORT, COL_SIGNAL]:
        print(f"Pre-fetching module metadata and resolved entities for graph-aware context...")
        # Get all modules and their metadata
        cursor = db.aql.execute(f"FOR m IN {COL_MODULE} RETURN {{id: m._id, label: m.label, summary: m.metadata.summary}}")
        for m in cursor:
            module_summaries[m['label']] = m.get('summary', '')
            module_labels[m['label']] = m['label']
        
        # Get resolved entities for each module (graph-aware context)
        resolved_query = f"""
        FOR edge IN {EDGE_RESOLVED}
            FILTER STARTS_WITH(edge._from, "{COL_MODULE}/")
            COLLECT module_id = edge._from INTO resolved_to = edge._to
            RETURN {{module_id: module_id, entities: resolved_to}}
        """
        try:
            resolved_cursor = db.aql.execute(resolved_query)
            for item in resolved_cursor:
                # Extract module name from full ID
                module_name = item['module_id'].split('/')[1]
                module_resolved_entities[module_name] = item['entities']
            print(f"  ✓ Found resolved entities for {len(module_resolved_entities)} modules")
        except Exception as e:
            logger.warning(f"Could not fetch module resolved entities: {e}")
            
    # We use a ThreadPool to parallelize remote AQL calls
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for item in items:
            context = ""
            parent_label = ""
            parent_entity_ids = None
            
            if col_name in [COL_PORT, COL_SIGNAL]:
                # Extract module name from ID (e.g., "RTL_Signal/or1200_except.esr" -> "or1200_except")
                parts = item['_key'].split('.')
                if len(parts) > 1:
                    mod_name = parts[0]
                    context = module_summaries.get(mod_name, "")
                    parent_label = module_labels.get(mod_name, "")
                    
                    # Graph-aware context: Get parent module's resolved entities
                    parent_entity_ids = module_resolved_entities.get(mod_name, None)
            
            # Add parent_label to the item for process_item_to_entity
            item_with_context = item.copy()
            item_with_context["parent_label"] = parent_label
            
            futures[executor.submit(
                process_item_to_entity, 
                db, 
                item_with_context, 
                view_name, 
                threshold, 
                method, 
                context,
                parent_entity_ids  # Pass graph-aware context
            )] = item
        
        for future in as_completed(futures):
            results = future.result()
            if results:
                resolved_edges.extend(results)

    if resolved_edges:
        print(f"Inserting {len(resolved_edges)} edges for {col_name}...")
        if not db.has_collection(EDGE_RESOLVED):
            db.create_collection(EDGE_RESOLVED, edge=True)
        if truncate:
            db.collection(EDGE_RESOLVED).truncate()
        db.collection(EDGE_RESOLVED).import_bulk(resolved_edges)
        
        # Count how many used graph-aware context
        graph_aware_count = sum(1 for e in resolved_edges if e.get('graph_aware', False))
        if graph_aware_count > 0:
            print(f"  ✓ {graph_aware_count} edges used graph-aware context boost")
    print(f"Completed {col_name} bridging.")

def process_logic_chunk(db, chunk, view_name):
    code = chunk.get("metadata", {}).get("code", "")
    if not code:
        return []
    
    identifiers = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', code)
    if not identifiers:
        return []
        
    search_terms = list(set(identifiers))
    
    query = f"""
    FOR doc IN {view_name}
      SEARCH ANALYZER(doc.content IN @terms, "text_en")
      FILTER IS_SAME_COLLECTION(@chunks_col, doc)
      SORT BM25(doc) DESC
      LIMIT 2
      RETURN {{id: doc._id, content: doc.content, score: BM25(doc)}}
    """
    
    candidates = list(db.aql.execute(query, bind_vars={
        "terms": search_terms,
        "chunks_col": COL_CHUNKS
    }))

    results = []
    for cand in candidates:
        if cand['score'] > 5.0:
            results.append({
                "_from": chunk["_id"],
                "_to": cand["id"],
                "score": cand['score'],
                "method": "logic_references_bm25_v2"
            })
    return results

def bridge_logic_parallel(db, view_name):
    print(f"Bridging LogicChunks in parallel...")
    chunks = list(db.collection(COL_LOGIC).all())
    print(f"Found {len(chunks)} logic chunks.")

    referenced_edges = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_logic_chunk, db, chunk, view_name): chunk for chunk in chunks}
        
        for future in as_completed(futures):
            results = future.result()
            if results:
                referenced_edges.extend(results)

    if referenced_edges:
        print(f"Inserting {len(referenced_edges)} {EDGE_REFERENCES} edges...")
        if not db.has_collection(EDGE_REFERENCES):
            db.create_collection(EDGE_REFERENCES, edge=True)
        db.collection(EDGE_REFERENCES).truncate()
        db.collection(EDGE_REFERENCES).import_bulk(referenced_edges)
    print("Logic chunk bridging complete.")

def bridge_all():
    db = get_db()
    view_name = create_search_view(db)
    
    start_time = time.time()
    
    # Stage 1: Architectural Bridging (Truncate first)
    print("\n--- Stage 1: Architectural Bridging ---")
    bridge_collection_parallel(db, COL_BUS, view_name, 0.5, "arch_bridging_bus", truncate=True)
    bridge_collection_parallel(db, COL_CLOCK, view_name, 0.5, "arch_bridging_clock")
    bridge_collection_parallel(db, COL_FSM, view_name, 0.5, "arch_bridging_fsm")
    bridge_collection_parallel(db, COL_PARAMETER, view_name, 0.5, "arch_bridging_param")
    bridge_collection_parallel(db, COL_MEMORY, view_name, 0.5, "arch_bridging_mem")
    
    # Stage 2: Structural Bridging (Append)
    print("\n--- Stage 2: Structural Bridging ---")
    bridge_collection_parallel(db, COL_MODULE, view_name, 0.7, "module_bridging_v2_poly")
    
    # Stage 3: Granular Bridging (Append)
    print("\n--- Stage 3: Granular Bridging ---")
    bridge_collection_parallel(db, COL_PORT, view_name, 0.6, "deep_bridging_v2_p")
    bridge_collection_parallel(db, COL_SIGNAL, view_name, 0.6, "deep_bridging_v2_s")
    
    # Stage 4: Logic Reference Bridging
    print("\n--- Stage 4: Logic Reference Bridging ---")
    bridge_logic_parallel(db, view_name)
    
    end_time = time.time()
    print(f"\nBridging Complete in {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    bridge_all()
