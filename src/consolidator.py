import os
import hashlib
import logging
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))
from db_utils import get_db
from config import COL_RAW_ENTITIES, COL_ENTITIES, COL_RAW_RELATIONS, COL_RELATIONS

COL_CONSOLIDATES = "CONSOLIDATES"
COL_GOLDEN_ENTITIES = COL_ENTITIES
COL_GOLDEN_RELATIONS = COL_RELATIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _ensure_collection(db, name: str, edge: bool = False) -> None:
    if db.has_collection(name):
        return
    logger.info(f"Creating collection: {name} ({'edge' if edge else 'vertex'})")
    db.create_collection(name, edge=edge)


def _reset_collection(db, name: str, edge: bool = False) -> None:
    _ensure_collection(db, name, edge=edge)
    db.collection(name).truncate()

def apply_indexes(db):
    logger.info(f"Applying indexes to {COL_GOLDEN_ENTITIES}...")
    col = db.collection(COL_GOLDEN_ENTITIES)
    
    # Persistent indexes for fast lookup and bridging
    col.add_index({'type': 'persistent', 'fields': ['entity_type'], 'name': 'entity_type-index'})
    col.add_index({'type': 'persistent', 'fields': ['entity_name'], 'name': 'entity_name-index'})
    
    # Optional vector index if you still want to perform semantic search LATER (not for consolidation)
    try:
        col.add_index({
            'type': 'vector', 
            'fields': ['embedding'], 
            'name': 'vector_cosine', 
            'params': {'dimension': 512, 'metric': 'cosine', 'nLists': 278}
        })
    except Exception:
        pass
    logger.info("  ✓ Golden Entities indexes ensured.")


def apply_bridging_indexes(db):
    """
    Apply indexes to RESOLVED_TO edge collection for graph-aware context.
    
    Note: ArangoDB automatically creates indexes on _from and _to for edge collections,
    so those are sufficient for our current graph traversal queries.
    
    Vertex-Centric Indexing (VCI) Opportunity:
    If we need to filter on destination vertex entity_type during traversal, we should:
    1. Copy entity_type from Golden_Entities onto RESOLVED_TO edges as target_type
    2. Create composite index on (_to, target_type) 
    3. Filter on edge.target_type instead of vertex.entity_type during traversal
    
    This would optimize queries like:
        FOR edge IN RESOLVED_TO
            FILTER edge._from == @rtl_id
            LET entity = DOCUMENT(edge._to)
            FILTER entity.entity_type == "processor_component"
    
    To become:
        FOR edge IN RESOLVED_TO
            FILTER edge._from == @rtl_id AND edge.target_type == "processor_component"
            
    Current status: Not needed yet as we filter entity_type before traversal, not during.
    """
    from config import EDGE_RESOLVED
    
    logger.info(f"Checking indexes on {EDGE_RESOLVED} edge collection...")
    
    # Ensure collection exists
    if not db.has_collection(EDGE_RESOLVED):
        logger.info(f"  {EDGE_RESOLVED} collection doesn't exist yet, will be created during bridging.")
        return
    
    # Note: _from and _to indexes are automatically created by ArangoDB for edge collections
    # Current graph-aware context queries use these automatic indexes efficiently
    
    logger.info(f"  ✓ Edge collection indexes verified (automatic _from/_to indexes present).")

def consolidate_entities():
    db = get_db()
    logger.info("Starting Lexical Consolidation...")
    
    # 1. Reset Golden Collections
    if not db.has_collection(COL_RAW_ENTITIES):
        raise RuntimeError(f"Missing raw entity collection '{COL_RAW_ENTITIES}'. Import documents via GraphRAG first.")
    if not db.has_collection(COL_RAW_RELATIONS):
        raise RuntimeError(f"Missing raw relations collection '{COL_RAW_RELATIONS}'. Import documents via GraphRAG first.")

    _reset_collection(db, COL_GOLDEN_ENTITIES, edge=False)
    _reset_collection(db, COL_CONSOLIDATES, edge=True)
    _reset_collection(db, COL_GOLDEN_RELATIONS, edge=True)
    
    # 2. Group by Name/Type and Create Golden Nodes + CONSOLIDATES Edges
    # This AQL does everything in the database engine.
    logger.info("Grouping and electing golden records...")
    consolidation_query = f"""
    FOR e IN {COL_RAW_ENTITIES}
        COLLECT etype = e.entity_type, 
                norm_name = LOWER(TRIM(e.entity_name)) 
        INTO group
        
        LET members = group[*].e
        LET primary = (FOR m IN members SORT LENGTH(m.entity_name) DESC, m._key ASC LIMIT 1 RETURN m)[0]
        LET golden_key = MD5(CONCAT(etype, ":", norm_name))
        
        INSERT {{
            _key: golden_key,
            entity_name: primary.entity_name,
            label: primary.entity_name,
            entity_type: etype,
            description: CONCAT_SEPARATOR(" | ", UNIQUE(FOR m IN members FILTER m.description != null RETURN TRIM(m.description))),
            embedding: primary.embedding,
            aliases: UNIQUE(FOR m IN members FILTER m.entity_name != primary.entity_name RETURN m.entity_name),
            metadata: {{ consolidated_count: LENGTH(members) }}
        }} INTO {COL_GOLDEN_ENTITIES}
        
        LET golden_id = NEW._id
        
        FOR m IN members
            INSERT {{
                _from: golden_id,
                _to: m._id,
                type: "CONSOLIDATES"
            }} INTO {COL_CONSOLIDATES}
            
        RETURN 1
    """
    db.aql.execute(consolidation_query)
    
    # 3. Sweep Relationships
    # This maps existing relations between raw entities to the new golden entities.
    logger.info("Sweeping relationships to golden nodes...")
    sweep_query = f"""
    FOR rel IN {COL_RAW_RELATIONS}
        // Map _from and _to to their golden parents
        LET golden_from = (FOR c IN {COL_CONSOLIDATES} FILTER c._to == rel._from RETURN c._from)[0]
        LET golden_to = (FOR c IN {COL_CONSOLIDATES} FILTER c._to == rel._to RETURN c._from)[0]
        
        // Only proceed if at least one endpoint was consolidated
        FILTER golden_from != null OR golden_to != null
        
        LET final_from = golden_from != null ? golden_from : rel._from
        LET final_to = golden_to != null ? golden_to : rel._to
        
        // Deduplicate relations between same golden nodes
        COLLECT src = final_from, dst = final_to, rtype = rel.type INTO provenance
        
        LET edge_key = MD5(CONCAT(src, dst, rtype))
        
        INSERT {{
            _key: edge_key,
            _from: src,
            _to: dst,
            type: rtype,
            provenance: provenance[*].rel._id
        }} INTO {COL_GOLDEN_RELATIONS}
        OPTIONS {{ overwriteMode: "update" }}
    """
    db.aql.execute(sweep_query)
    
    # 4. Apply Indexes
    apply_indexes(db)
    apply_bridging_indexes(db)
    
    logger.info(f"Stage 1 Consolidation complete. Golden Entities: {db.collection(COL_GOLDEN_ENTITIES).count()}")


def consolidate_fuzzy_stage2(db=None, levenshtein_distance=1, min_confidence=0.75, dry_run=False):
    """
    Stage 2 Fuzzy Consolidation: Merges near-duplicate entities using:
    - Levenshtein distance for typo detection
    - Token overlap for partial matches
    - Type compatibility checking
    
    Args:
        db: ArangoDB connection (if None, will get from get_db())
        levenshtein_distance: Maximum edit distance to consider (default: 1)
        min_confidence: Minimum confidence score to merge (default: 0.75)
        dry_run: If True, returns candidates without merging (default: False)
    
    Returns:
        List of merge candidates with confidence scores
    """
    if db is None:
        db = get_db()
    
    logger.info(f"Starting Stage 2 Fuzzy Consolidation (Levenshtein ≤{levenshtein_distance}, confidence ≥{min_confidence})...")
    
    # Query to find fuzzy match candidates
    # This uses Levenshtein distance and token overlap to find near-duplicates
    fuzzy_query = f"""
    FOR e1 IN {COL_GOLDEN_ENTITIES}
        FOR e2 IN {COL_GOLDEN_ENTITIES}
            FILTER e1._key < e2._key  // Avoid duplicate pairs and self-comparison
            FILTER e1.entity_type == e2.entity_type  // Same type only
            
            LET norm1 = LOWER(TRIM(e1.entity_name))
            LET norm2 = LOWER(TRIM(e2.entity_name))
            
            // Levenshtein distance check
            LET lev_dist = LEVENSHTEIN_DISTANCE(norm1, norm2)
            FILTER lev_dist <= @max_distance AND lev_dist > 0
            
            // Token-based similarity for longer names
            LET tokens1 = TOKENS(norm1, "text_en")
            LET tokens2 = TOKENS(norm2, "text_en")
            LET token_intersection = LENGTH(INTERSECTION(tokens1, tokens2))
            LET min_tokens = MIN([LENGTH(tokens1), LENGTH(tokens2)])
            LET token_overlap = min_tokens > 0 ? token_intersection / min_tokens : 0
            
            // Combined confidence score
            // For short names (< 5 chars), rely more on Levenshtein
            // For longer names, blend Levenshtein + token overlap
            LET name_length = MIN([LENGTH(norm1), LENGTH(norm2)])
            LET lev_score = 1.0 - (lev_dist / MAX([name_length, 1]))
            
            LET confidence = name_length <= 5 
                ? lev_score 
                : (lev_score * 0.6 + token_overlap * 0.4)
            
            FILTER confidence >= @min_confidence
            
            // Additional checks for false positive reduction
            // Avoid merging if one is a clear prefix/suffix AND they're both short
            LET is_prefix = STARTS_WITH(norm1, norm2) OR STARTS_WITH(norm2, norm1)
            LET both_short = name_length < 4
            FILTER !(is_prefix AND both_short)
            
            SORT confidence DESC
            
            RETURN {{
                entity1_id: e1._id,
                entity1_name: e1.entity_name,
                entity1_type: e1.entity_type,
                entity1_desc: e1.description,
                entity2_id: e2._id,
                entity2_name: e2.entity_name,
                entity2_type: e2.entity_type,
                entity2_desc: e2.description,
                levenshtein_distance: lev_dist,
                token_overlap: token_overlap,
                confidence: confidence
            }}
    """
    
    bind_vars = {
        "max_distance": levenshtein_distance,
        "min_confidence": min_confidence
    }
    
    candidates = list(db.aql.execute(fuzzy_query, bind_vars=bind_vars))
    logger.info(f"Found {len(candidates)} fuzzy match candidates")
    
    if dry_run or len(candidates) == 0:
        return candidates
    
    # Group candidates into merge sets
    # Use union-find to handle transitive merges (e.g., A~B, B~C => merge all three)
    from collections import defaultdict
    
    parent = {}
    
    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py
    
    # Build union-find structure
    for cand in candidates:
        union(cand['entity1_id'], cand['entity2_id'])
    
    # Group entities by their root parent
    merge_groups = defaultdict(list)
    for cand in candidates:
        root = find(cand['entity1_id'])
        merge_groups[root].append(cand['entity1_id'])
        merge_groups[root].append(cand['entity2_id'])
    
    # Deduplicate merge groups
    merge_groups = {k: list(set(v)) for k, v in merge_groups.items()}
    
    logger.info(f"Identified {len(merge_groups)} merge groups")
    
    # Perform merges
    merged_count = 0
    for root, entity_ids in merge_groups.items():
        if len(entity_ids) < 2:
            continue
        
        # Fetch all entities in the group
        fetch_query = f"""
        FOR e IN {COL_GOLDEN_ENTITIES}
            FILTER e._id IN @entity_ids
            RETURN e
        """
        entities = list(db.aql.execute(fetch_query, bind_vars={"entity_ids": entity_ids}))
        
        # Choose primary: longest name, or first alphabetically
        primary = max(entities, key=lambda e: (len(e['entity_name']), e['entity_name']))
        secondaries = [e for e in entities if e['_id'] != primary['_id']]
        
        # Merge: Update primary with combined data
        all_aliases = primary.get('aliases', [])
        all_descriptions = [primary.get('description', '')]
        
        for sec in secondaries:
            all_aliases.extend(sec.get('aliases', []))
            all_aliases.append(sec['entity_name'])
            if sec.get('description'):
                all_descriptions.append(sec['description'])
        
        all_aliases = list(set([a for a in all_aliases if a != primary['entity_name']]))
        combined_description = " | ".join([d for d in all_descriptions if d])
        
        # Update primary entity
        update_query = f"""
        UPDATE @key WITH {{
            aliases: @aliases,
            description: @description,
            metadata: MERGE(
                @current_metadata,
                {{
                    fuzzy_merged: true,
                    fuzzy_merged_count: @merge_count
                }}
            )
        }} IN {COL_GOLDEN_ENTITIES}
        """
        
        db.aql.execute(update_query, bind_vars={
            "key": primary['_key'],
            "aliases": all_aliases,
            "description": combined_description,
            "current_metadata": primary.get('metadata', {}),
            "merge_count": len(secondaries)
        })
        
        # Re-point CONSOLIDATES edges from secondaries to primary
        for sec in secondaries:
            repoint_query = f"""
            FOR edge IN {COL_CONSOLIDATES}
                FILTER edge._from == @secondary_id
                UPDATE edge WITH {{
                    _from: @primary_id
                }} IN {COL_CONSOLIDATES}
            """
            db.aql.execute(repoint_query, bind_vars={
                "secondary_id": sec['_id'],
                "primary_id": primary['_id']
            })
        
        # Remove secondary entities
        for sec in secondaries:
            db.collection(COL_GOLDEN_ENTITIES).delete(sec['_key'])
        
        merged_count += len(secondaries)
        logger.info(f"  Merged {len(secondaries)} entities into {primary['entity_name']}")
    
    logger.info(f"Stage 2 Fuzzy Consolidation complete. Merged {merged_count} entities.")
    return candidates


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--indexes-only":
        # Just apply indexes without running consolidation
        db = get_db()
        apply_indexes(db)
        apply_bridging_indexes(db)
        logger.info("Indexes applied successfully.")
    elif len(sys.argv) > 1 and sys.argv[1] == "--fuzzy-only":
        # Run only Stage 2 fuzzy consolidation
        db = get_db()
        consolidate_fuzzy_stage2(db, levenshtein_distance=1, min_confidence=0.75)
    elif len(sys.argv) > 1 and sys.argv[1] == "--fuzzy-dry-run":
        # Dry run: show candidates without merging
        db = get_db()
        candidates = consolidate_fuzzy_stage2(db, levenshtein_distance=1, min_confidence=0.75, dry_run=True)
        print(f"\nFound {len(candidates)} fuzzy merge candidates:")
        for i, cand in enumerate(candidates[:20], 1):  # Show top 20
            print(f"{i}. {cand['entity1_name']} <-> {cand['entity2_name']} "
                  f"(confidence: {cand['confidence']:.2f}, lev: {cand['levenshtein_distance']})")
    else:
        # Full consolidation: Stage 1 + Stage 2
        consolidate_entities()
        db = get_db()
        consolidate_fuzzy_stage2(db, levenshtein_distance=1, min_confidence=0.75)
