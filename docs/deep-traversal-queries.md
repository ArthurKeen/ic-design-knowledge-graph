# Deep Traversal AQL Queries

Paste each query into the ArangoDB web UI → **Query** tab → Run → click the **Graph** tab
to render the path as an interactive graph.

Both queries return `path` objects (`p.vertices[]` + `p.edges[]` — all `_id`/`_from`/`_to`
fields populated) which the ArangoDB Graph tab renders automatically.

---

## Query 1 — Exact 4-hop Semantic Bridge (single path, fully verified)

Traces the conceptual lineage from OR1200 documentation all the way to a concrete IBEX RTL
signal implementation:

```
OR1200:Development Interface
  →[OR1200_Golden_Relations]→  OR1200:Debug unit
  →[CROSS_REPO_SIMILAR_TO]→   IBEX:Debug Mode
  ←[RESOLVED_TO]←             RTL_Signal:debug_mode
  ←[HAS_SIGNAL]←              RTL_Module:ibex_core
```

Returns **1 path** in ~0.03 s.

```aql
// ─────────────────────────────────────────────────────────────────────────
// QUERY 1 — Exact 4-hop semantic bridge
//   Cross-repo path: OR1200 doc concept → OR1200:Debug unit
//                 → IBEX:Debug Mode → RTL signal → RTL module
//
// Edge direction legend (↔ = ANY in the traversal):
//   [0] OR1200_Golden_Relations   outbound   (golden entity → golden entity)
//   [1] CROSS_REPO_SIMILAR_TO     outbound   (OR1200 → IBEX)
//   [2] RESOLVED_TO               inbound    (RTL signal → golden, traversed backward)
//   [3] HAS_SIGNAL                inbound    (RTL module → RTL signal, traversed backward)
//
// Run in ArangoDB web UI → Query → click GRAPH tab to visualize
// ─────────────────────────────────────────────────────────────────────────
FOR v, e, p IN 4..4
    ANY 'OR1200_Golden_Entities/OR1200_g_666d09e70959'
    GRAPH 'IC_Temporal_Knowledge_Graph'
    OPTIONS { uniqueVertices: 'path', order: 'bfs' }

    FILTER REGEX_REPLACE(p.edges[0]._id, '/.*', '') == 'OR1200_Golden_Relations'
    FILTER REGEX_REPLACE(p.edges[1]._id, '/.*', '') == 'CROSS_REPO_SIMILAR_TO'
    FILTER REGEX_REPLACE(p.edges[2]._id, '/.*', '') == 'RESOLVED_TO'
    FILTER REGEX_REPLACE(p.edges[3]._id, '/.*', '') == 'HAS_SIGNAL'
    FILTER p.vertices[1].name == 'Debug unit'

    RETURN p
```

---

## Query 2 — Open-ended Deep Traversal (depth 3–4, cross-repo subgraph)

Explores all paths of 3–4 hops from OR1200:Debug unit that cross at least two repositories.
Starts at the semantic bridge anchor, naturally reaching IBEX concepts, MAROCCHINO
counterparts, and the underlying IBEX RTL implementation.

Returns **927 matching paths**; LIMIT 25 shown (≈0.2 s). The Graph tab merges all 25 paths
into one connected subgraph — typically 10–15 unique nodes and 20–30 unique edges.

```aql
// ─────────────────────────────────────────────────────────────────────────
// QUERY 2 — Open-ended deep traversal (depth 3–4, cross-repo)
//   Anchor:  OR1200:Debug unit  (sits at the OR1200 ↔ IBEX semantic bridge)
//   Filter:  path must cross at least 2 repositories
//   Depth 3 paths reach: IBEX golden entities, MAROCCHINO counterparts,
//                        RTL_Signal:debug_mode → RTL_Module:ibex_core
//   Depth 4 paths reach: IBEX RTL signals, IBEX chunks, IBEX spec concepts
//
// Returns path objects — Graph tab renders the full connected subgraph.
// Increase LIMIT (max ~100 before UI slows) to widen the subgraph.
// ─────────────────────────────────────────────────────────────────────────
FOR v, e, p IN 3..4
    ANY 'OR1200_Golden_Entities/OR1200_g_bd5d34270ec4'
    GRAPH 'IC_Temporal_Knowledge_Graph'
    OPTIONS { order: 'bfs', uniqueVertices: 'path' }

    LET repos = (
        FOR pv IN p.vertices
            FILTER pv.repo != null
            RETURN DISTINCT pv.repo
    )
    FILTER LENGTH(repos) >= 2

    LIMIT 25
    RETURN p
```

---

## Node IDs Reference

| ID | Description |
|---|---|
| `OR1200_Golden_Entities/OR1200_g_666d09e70959` | OR1200: Development Interface |
| `OR1200_Golden_Entities/OR1200_g_bd5d34270ec4` | OR1200: Debug unit |
| `RTL_Module/IBEX_ibex_core` | IBEX: `ibex_core` RTL top-level module |

---

## Depth Counts (from OR1200:Debug unit, any direction, repos ≥ 2)

| Depth | # Paths |
|---|---|
| 3 | 59 (includes RTL_Signal:debug_mode → RTL_Module:ibex_core) |
| 4 | 868 (extends into IBEX RTL signals, chunks, spec relations) |

---

## Data Quality Notes

- **False positive cleanup (2026-03-15)**: 13 `RESOLVED_TO` edges linking SRAM `di` (data-input)
  ports to the `Development Interface` golden entity were removed. Root cause: the acronym `DI`
  was auto-generated from "Development Interface" and entered the word-index, matching any
  2-char `di` port. `SKIP_NAMES` in `src/rtl_semantic_bridge.py` now includes `di`, `do`, `we`,
  `oe`, `cs`, `ce`, `qi`, `qo` to prevent recurrence.
- **Isolated IBEX leaf nodes**: some `CROSS_REPO_SIMILAR_TO` edges connect "leaf" entities that
  have no further RTL or documentation connections in the target repo, resulting in short paths
  that terminate without reaching RTL. This is a data completeness issue (not all IBEX modules
  have been fully resolved), not a query bug.
