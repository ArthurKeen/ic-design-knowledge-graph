# IC Knowledge Graph — Cursor Handoff Notes
_Branch: `feature/temporal-kg` — Last updated: 2026-03-15 (Session 2)_

---

## What Was Just Completed (Session 2)

All 4 original handoff priorities are done plus post-priority hardening work.

### Priority 1 — 8 New Tests ✅
Added to `tests/test_local_graphrag.py`. Full suite now **32/32 green** in offline/restricted
environments (sentence-transformer and pipeline embedder calls are mocked).

New tests added:
- `TestGoldenDedup.test_golden_entity_has_labels`
- `TestGoldenDedup.test_golden_entity_version_tracking`
- `TestLoader.test_consolidates_edge_has_lpg_fields`
- `TestLoader.test_mentioned_in_edge_has_lpg_fields`
- `TestLoader.test_raw_entity_has_labels`
- `TestExtractorParsing.test_entity_type_override`
- `TestExtractorParsing.test_relation_type_normalisation`
- `TestExtractorParsing.test_relation_type_enforcement`

Run: `PYTHONPATH=src pytest tests/test_local_graphrag.py -v`

### Priority 2 — MAROCCHINO RESOLVED_TO Coverage ✅
Original approach (`--min-score 0.65`) was investigated and **explicitly rejected** — scores in
that band have zero lexical token overlap with targets (15/21 candidates), and several are
semantically incorrect (e.g. `Wishbone Reset → Tick Timer`).

Instead, three complementary improvements were implemented (see "Files Changed" below):
1. **Safer acronym tokenization** (`src/utils.py`) — ALLCAPS tokens no longer split to `O P T I O N`
2. **Repo-specific acronym dictionaries** (`src/etl_rtl.py` + `src/marocchino_acronyms.json`)
3. **Alias-aware exact matching + embedding acceptance gates** (`src/rtl_semantic_bridge.py` +
   `src/rtl_semantic_aliases.json`)

MAROCCHINO result: **12 exact + 0 embedding = 12 edges at 0.72** (all high-confidence).
Applied at `--min-score 0.70` for the run.

### Priority 3 — GraphRAG Re-Ingestion with LPG Schema ✅
All four repos truncated and re-ingested. Zero `null` labels on any golden entity.

| Repo | Entities | Golden | Chunks | Communities | `null labels` |
|---|---:|---:|---:|---:|---:|
| OR1200 | 164 | 164 | 10 | 72 | 0 |
| MOR1KX | 40 | 40 | 3 | 16 | 0 |
| MAROCCHINO | 85 | 85 | 5 | 39 | 0 |
| IBEX | 557 | 552 | 51 | 177 | 0 |

### Priority 4 — Cross-Repo Bridge Rebuild ✅
Rebuilt `CROSS_REPO_SIMILAR_TO` and `CROSS_REPO_EVOLVED_FROM` after re-ingestion.

| Pair | Similar | Notes |
|---|---:|---|
| OR1200 ↔ MOR1KX | 9 | 6 embedding + 3 structural |
| OR1200 ↔ MAROCCHINO | 13 | 11 embedding + 2 structural |
| OR1200 ↔ IBEX | 17 | 15 embedding + 2 structural |
| MOR1KX ↔ MAROCCHINO | 3 | 2 embedding + 1 structural |
| MOR1KX ↔ IBEX | 2 | 0 embedding + 2 structural |
| MAROCCHINO ↔ IBEX | 9 | 9 embedding + 0 structural |
| **TOTAL** | **53** | |

`CROSS_REPO_EVOLVED_FROM`: **1** (MOR1KX → OR1200 lineage rule)

### Post-Priority Hardening ✅
Full `RESOLVED_TO` rebuild + named graph + index rebuild.

---

## Final Frozen RESOLVED_TO Table

Built with precision-first policy: alias-aware exact match first, gated embeddings.
Default threshold `0.72`; MAROCCHINO run at `0.70` to allow alias-matched Wishbone/SPR terms.

| Repo | Exact | Embedding | Total |
|---|---:|---:|---:|
| OR1200 | 101 | 8 | **109** |
| MOR1KX | 0 | 42 | **42** |
| MAROCCHINO | 12 | 0 | **12** |
| IBEX | 32 | 24 | **56** |
| **TOTAL** | **145** | **74** | **219** |

---

## Files Changed (Session 2)

| File | What Changed |
|---|---|
| `tests/test_local_graphrag.py` | +8 tests; mocked `_embed_sentence_transformers` and `embed_entities` for offline runs |
| `src/utils.py` | `expand_acronym()`: safer CamelCase split (lower→upper boundary only); non-alnum separator split |
| `src/etl_rtl.py` | `parse_verilog_files()`: repo-specific acronym dict loader (`<repo>_acronyms.json`); removed global OR1200 dict fallback |
| `src/rtl_semantic_bridge.py` | `load_golden_entities()`: fetches `aliases` field + merges curated overrides + acronym aliases; `match_exact()`: indexes aliases+names; `match_embedding()`: records `second_best` score; new `_embedding_gate()`: rejects context drift, requires token overlap or very strong lead |
| `src/marocchino_acronyms.json` | **NEW** — 12-entry MAROCCHINO-specific acronym dict (`wb`, `pic`, `du`, `dmmu`, `lsu`, `ic`, `dc`, `epcr`, `npc`, `ifetch`, `ctrl`, `immu`) |
| `src/rtl_semantic_aliases.json` | **NEW** — curated per-repo alias overrides for golden entities (`MAROCCHINO_` section: Wishbone clock, PIC, DU SPRs, EPCR, SPR EVBAR, pipeline_flush) |

---

## Key Architecture Decisions (do not reverse)

1. **Shared RTL collections** (`RTL_Port`, `RTL_Signal`, etc.) — `repo` field discriminates.
2. **LPG schema on edges** — every edge has `fromNodeType + toNodeType + labels:[...]`.
3. **Golden entity `labels` list** — `["GoldenEntity", "REGISTER", "OR1200"]` — enables type-scan-free AQL filters.
4. **`RESOLVED_TO` is shared** — per-repo scoped by `repo` field on each edge.
5. **MAROCCHINO threshold stays at `0.70`** — `0.65` was investigated and rejected (coin-toss precision). Use alias file + embedding gates instead.
6. **`--min-score 0.65` is a known landmine** — do not apply globally. Any future expansion of MAROCCHINO coverage must go through the alias file first.

---

## Running the Stack

```bash
# Activate venv
source .venv/bin/activate
export PYTHONPATH=src

# Run all tests (no network required)
pytest tests/ -v

# RTL extraction (all repos, skip clone+temporal+graphrag)
python3 scripts/multi_repo/ingest_repo.py --all --no-clone --no-temporal --no-graphrag

# Rebuild semantic bridge (precision-first, all repos)
python3 src/rtl_semantic_bridge.py --all --truncate

# MAROCCHINO only at tuned threshold (if rerunning individually)
python3 src/rtl_semantic_bridge.py --repo MAROCCHINO_ --min-score 0.70

# Rebuild named graph + indexes
python3 scripts/temporal/create_temporal_graph.py

# Rebuild cross-repo bridge
python3 src/cross_repo_bridge.py --all

# Full re-ingest (GraphRAG only, all repos — requires OpenAI key, ~30 min)
python3 scripts/multi_repo/ingest_repo.py --no-clone --no-temporal --no-rtl

# Dry-run bridge for one repo
python3 src/rtl_semantic_bridge.py --repo IBEX_ --dry-run
```

---

## DB Connection
Values in `.env`:
```
ARANGO_ENDPOINT=https://5ieeavs2.rnd.pilot.arango.ai
ARANGO_DATABASE=ic-knowledge-graph-temporal
ARANGO_USERNAME=...
ARANGO_PASSWORD=...
```

Named graph: `IC_Temporal_Knowledge_Graph` — 21 edge definitions, 29 edge collections with
vertex-centric indexes (`_from,toNodeType`) and (`_to,fromNodeType`).

---

## What Still Needs to Be Done

1. **Expand `rtl_semantic_aliases.json`** for OR1200, MOR1KX, IBEX repos — same pattern as
   MAROCCHINO. Currently only MAROCCHINO has curated aliases.
2. **MOR1KX exact-match recovery** — 0 exact matches currently (all 42 are embedding).
   Add `src/mor1kx_acronyms.json` and curate aliases for its golden entities.
3. **`python-igraph` install** — community detection currently uses label-propagation fallback.
   `pip install python-igraph` enables Leiden algorithm for better community quality.
4. **GraphRAG re-ingestion with `doc_version`** — current re-ingest does not tag `doc_version`
   or `valid_from_epoch`. Pass `--doc-version` when re-ingesting for temporal tracking.
5. **OR1200 exact-match count watch** — 101 exact matches include some via broad word-indexing
   (single words ≥ 4 chars from golden names). Consider tightening the word-level index if
   false positives appear in traversal QA.
