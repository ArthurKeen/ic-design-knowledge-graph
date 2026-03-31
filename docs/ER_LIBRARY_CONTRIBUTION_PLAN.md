# Entity Resolution Library — Contribution Plan (Revised)
_Drafted: 2026-03-16 | Revised: 2026-03-18 | Revised again: 2026-03-25_
_ER Library version assessed: **3.3.1** (`arango-entity-resolution` at `~/code/arango-entity-resolution`)_

This document captures entity-resolution techniques proven in the IC Knowledge Graph
project and defines how to contribute them to `arango-entity-resolution` safely,
with stable APIs, explicit rollout controls, and measurable quality/performance gates.

---

## 1) Background: What the IC Project Proved

The `RESOLVED_TO` semantic bridge (RTL nodes → golden entities) is an ER task:
~7,000 source records matched against ~600 targets with a precision-first workflow.
Three production-like experimental cycles validated reusable patterns:

- cross-collection matching with schema mismatch
- multi-stage matching (`exact/alias` before embedding)
- precision gates (margin, token overlap, contextual type affinity)
- alias expansion for early-stage recall
- structural similarity for sparse-text records

These patterns are transferable, but they must be integrated into the library
without domain hardwiring or unstable API growth.

---

## 2) Current State of `arango-entity-resolution` (v3.3.1)

Since the original plan was drafted, the library has undergone major evolution.
This section captures what exists today so contributions target real gaps.

### 2.1 Capabilities Already Present

| Capability | Library Module | Status |
|---|---|---|
| Cross-collection matching | `CrossCollectionMatchingService` + MCP `resolve_entity_cross_collection` | **Shipped (3.2.x)** |
| Configurable ER pipeline | `ConfigurableERPipeline` (YAML/JSON config) | **Shipped (3.2.x)** |
| Incremental single-record matching | `IncrementalResolver` | **Shipped (3.2.x)** |
| Golden record persistence | `GoldenRecordPersistenceService` + `resolvedTo` edges | **Shipped (3.1.1)** |
| Deterministic / SmartGraph edge keys | `SimilarityEdgeService` | **Shipped (3.2.3)** |
| Graph traversal blocking | `GraphTraversalBlockingStrategy` | **Shipped (3.1.x)** |
| Vector/ANN blocking | `ANNAdapter` + `VectorBlockingStrategy` | **Shipped (3.2.x)** |
| WCC clustering (multi-backend) | `WCCClusteringService` (DFS, union-find, sparse, AQL) | **Shipped (3.3.x)** |
| LLM match verification | `LLMMatchVerifier` + active learning hooks | **Shipped (3.2.x)** |
| Node2Vec graph embeddings | `Node2VecEmbeddingService` | **Shipped (3.2.x)** |
| MCP server (15+ tools) | `entity_resolution.mcp.server` | **Shipped (3.2.x)** |
| `explain_match` (basic) | MCP tool | **Shipped (3.2.x)** |
| `er_options_schema_version` | MCP responses | **Shipped (3.2.x)** |
| Field transformers | `strip`, `e164`, `metaphone`, `state_code`, etc. | **Shipped (3.2.x)** |
| Enrichments (type filter, acronym, hierarchy) | `TypeCompatibilityFilter`, `AcronymExpansionHandler`, `HierarchicalContextResolver` | **Shipped (3.1.0)** |
| Runtime quality gates / baselines | `RuntimeQualityService` + CI baselines | **Shipped (3.3.x)** |
| Auto clustering backend selection | Threshold-based auto selection | **Shipped (3.4.0-dev)** |

### 2.2 Remaining Gaps (What Still Needs Contributing)

| IC Pattern | Library Gap | Plan Ref |
|---|---|---|
| Multi-stage pipeline (`exact` → `embedding`) as unified config | `ConfigurableERPipeline` supports stages but not the explicit `options["stages"]` contract from §3.1 | A2 |
| Score-margin gate | No `min_margin` gating in matching pipeline | A3 |
| Token-overlap gate + domain stopwords | No `require_token_overlap` or `word_index_stopwords` gating | A4 |
| Contextual type-affinity as pipeline gate | `TypeCompatibilityFilter` exists as enrichment but not as a rejection gate in matching | A4b (partial) |
| Gate failure diagnostics in `explain_match` | `explain_match` exists but doesn't emit pass/fail by gate type | A5 |
| Full alias expansion pipeline (multi-source, secure) | `AcronymExpansionHandler` covers acronyms only; plan's multi-source model (field, managed_ref, inline, auto-acronym) is richer | A6 (partial) |
| Structural token-Jaccard for list features | String-level Jaccard exists; list/set Jaccard for structured features (e.g. port signatures) does not | A7 |

### 2.3 New Library Capabilities Not Anticipated by Original Plan

The following capabilities were added to the library after the plan was drafted.
Contributions should align with these patterns rather than introducing parallel ones:

- **YAML-driven `ConfigurableERPipeline`** — new contributions should integrate as
  pipeline stages/configs, not as standalone functions.
- **Pluggable clustering backends** — IC community detection stays project-local (B3).
- **LLM match verification** — contributes to explainability; gate diagnostics (A5)
  should augment this, not replace it.
- **Runtime quality baselines** — new gates (A3/A4/A4b) should emit metrics
  compatible with the existing `RuntimeQualityService` baseline framework.
- **`IncrementalResolver`** — single-record matching; alias expansion (A6) must work
  in both batch and incremental modes.

---

## 3) Design Principles for Contributions

1. **Neutral by default:** no IC-specific token sets, type names, or stopwords.
2. **Pipeline-native:** integrate into `ConfigurableERPipeline` as stages, gates,
   or enrichments — not as standalone top-level functions.
3. **Calibrated gates:** no new precision gate should be enabled without dataset calibration.
4. **Observable behavior:** all acceptance/rejection gates emit diagnostics compatible
   with `RuntimeQualityService`.
5. **Safe rollout:** introduce features in shadow/report-only mode before enforcement.
6. **MCP parity:** every library capability must be reflected in MCP tool contracts.

---

## 4) API Strategy (Updated for v3.3.1)

The library's architecture has evolved to use `ConfigurableERPipeline` with
YAML/JSON configuration. Contributions should follow this pattern.

### 4.1 Stage-based pipeline configuration

Instead of the original `options` dict proposal, align with the existing
`ERPipelineConfig` YAML model:

```yaml
entity_resolution:
  blocking:
    strategy: "hybrid"
    fields: ["name", "aliases"]
  similarity:
    algorithm: "jaro_winkler"
    fields:
      - field: "name"
        weight: 0.7
      - field: "description"
        weight: 0.3
  # NEW: multi-stage (A2)
  stages:
    - type: "exact"
      fields: ["name", "aliases"]
      score: 1.0
    - type: "embedding"
      field: "description"
      min_score: 0.72
  # NEW: precision gating (A3/A4/A4b)
  gating:
    min_margin: 0.10           # A3
    require_token_overlap: false  # A4
    token_overlap_bypass_score: 0.95
    word_index_stopwords: []     # domain-specific, not hardcoded
    type_affinity:               # A4b
      enabled: false
      target_type_field: "type"
      compatibility_map: {}
  # NEW: alias expansion (A6)
  aliasing:
    sources:
      - type: "field"
        field: "aliases"
      - type: "acronym"
        auto: true
        min_word_len: 4
```

### 4.2 Cross-collection matching

Already available via `CrossCollectionMatchingService`. Contributions enhance it with:

- Stage-based matching within cross-collection workflow (A2)
- Gating support (A3/A4/A4b)
- Alias expansion pre-processing (A6)

### 4.3 MCP tool contract updates

Extend existing `find_duplicates` and `resolve_entity_cross_collection` tools
with optional `gating`, `stages`, and `aliasing` parameters in the nested
`options` object. MCP schema versioning (`er_options_schema_version`) is
already in place.

---

## 5) Contribution Scope (Library)

### A1. Cross-Collection / Heterogeneous ER ✅ SHIPPED

`CrossCollectionMatchingService` + MCP `resolve_entity_cross_collection` shipped
in v3.2.x. No further contribution needed.

**Remaining enhancement:** wire stages/gating/aliasing (A2–A6) into the
cross-collection path once those are available.

---

### A2. Multi-Stage Pipeline Strategy (`exact_then_embedding`)

**Goal:** Run cheap/high-precision stages first and only escalate unmatched records.

**Contribution:** Add `stages` config key to `ERPipelineConfig`:

```yaml
stages:
  - type: "exact"
    fields: ["name", "aliases"]
    score: 1.0
  - type: "embedding"
    field: "description"
    min_score: 0.72
```

**Integration point:** `ConfigurableERPipeline.run()` — short-circuit records
matched at earlier stages. Each stage emits its own timing/count metrics.

---

### A3. Score-Margin Gate

**Goal:** Reject ties/noisy near-ties even when absolute score passes.

**Contribution:** `gating.min_margin` config key. When the top candidate's score
minus the second-best is less than `min_margin`, the match is rejected.

**Integration point:** Post-similarity, pre-edge-creation in the pipeline.

---

### A4. Token-Overlap Gate + Domain Stopwords

**Goal:** Reduce semantic false positives where lexical grounding is absent.

**Contribution:**

- `gating.require_token_overlap` — boolean, default `false`
- `gating.token_overlap_bypass_score` — skip gate for very high scores
- `gating.word_index_stopwords` — list of strings to exclude from overlap check

Default behavior remains unchanged unless enabled.

---

### A4b. Contextual Type-Affinity Gate (Enhance Existing Enrichment)

**Goal:** Enforce soft type compatibility based on source-token context.

**Current state:** `TypeCompatibilityFilter` exists as an enrichment but is not
integrated as a pipeline rejection gate.

**Contribution:** Wire `TypeCompatibilityFilter` into the gating framework so it
can operate as a configurable gate with shadow/report/enforcement modes. Add
`gating.type_affinity.enabled`, `gating.type_affinity.target_type_field`,
`gating.type_affinity.compatibility_map` to config.

---

### A5. `explain_match` Enhancement: Gate Failure Diagnostics

**Goal:** Explain why high-scoring candidates were rejected.

**Current state:** `explain_match` MCP tool exists but doesn't emit gate-level
pass/fail diagnostics.

**Contribution:** Add `gates` section to `explain_match` output:

```json
{
  "gates": [
    {"gate": "margin", "passed": true, "margin": 0.15},
    {"gate": "token_overlap", "passed": false, "overlap": 0.0,
     "reason": "No shared tokens between 'di' and 'Development Interface'"}
  ],
  "gate_failures": ["token_overlap"]
}
```

**Integration point:** Augments existing `explain_match` response schema.

---

### A6. Alias / Synonym Expansion (Enhance Existing Enrichment)

**Goal:** Improve exact-stage recall for abbreviations/acronyms/synonyms.

**Current state:** `AcronymExpansionHandler` handles auto-generated acronyms.
The plan calls for a richer multi-source model.

**Contribution:** Extend aliasing subsystem to support:

```yaml
aliasing:
  sources:
    - type: "field"          # existing document field
      field: "aliases"
    - type: "managed_ref"    # server-side reference (MCP secure)
      ref: "entity_aliases_v1"
    - type: "inline"         # caller-provided map
      map: {"lsu": "load store unit"}
    - type: "acronym"        # auto-generate (existing handler)
      auto: true
      min_word_len: 4
```

**Security note:** `managed_ref` avoids arbitrary filesystem paths in MCP mode.

**Integration point:** Pre-blocking enrichment in `ConfigurableERPipeline`.

---

### A7. Structural Token-Jaccard Similarity

**Goal:** Provide robust matching where descriptive text is sparse or absent.

**Current state:** `WeightedFieldSimilarity` supports string-level `jaccard`.
Plan calls for set/list-level Jaccard on structured features.

**Contribution:** Add `token_jaccard` similarity variant that:

- Tokenizes field values into sets (splitting on delimiters)
- Computes Jaccard on token sets rather than character-level
- Supports `weighted_jaccard` with size-match bonus (as in IC's
  `_port_signature_similarity`)

**Integration point:** New algorithm option in `WeightedFieldSimilarity`.

---

## 6) Sequencing (Revised for v3.3.1)

### C1 — Cross-collection linking foundation ✅ DONE

Already shipped. No further work.

### C2 — Multi-stage pipeline

- Library: A2
- Integration: `ConfigurableERPipeline` stage config
- MCP: `find_duplicates` + `resolve_entity_cross_collection` accept `stages` config
- Acceptance: stage-level timing metrics; records resolved at stage N don't enter stage N+1

### C3a — Core precision gates

- Library: A3 + A4
- Integration: gating framework in pipeline post-similarity step
- MCP: `options.gating.{min_margin, require_token_overlap, ...}`
- Acceptance: shadow mode produces calibration report before enforcement

### C3b — Contextual type affinity (enhance enrichment → gate)

- Library: A4b
- Integration: wire existing `TypeCompatibilityFilter` into gating framework
- MCP: `options.gating.type_affinity.*`
- Prerequisite: C3a (gating framework must exist)

### C4 — Explainability enrichment

- Library: A5
- Integration: augment existing `explain_match` response
- MCP: schema update for `explain_match` response
- Prerequisite: C3a (gates must exist to report on)

### C5 — Alias expansion (enhance enrichment)

- Library: A6
- Integration: extend `AcronymExpansionHandler` or add sibling enrichment
- MCP: `options.aliasing`
- Must work in both batch (`ConfigurableERPipeline`) and incremental
  (`IncrementalResolver`) modes

### C6 — Structural token-Jaccard

- Library: A7
- Integration: new algorithm in `WeightedFieldSimilarity`
- MCP: `options.similarity`

### Project refactor dependencies

- After C2 + C3a + C3b: refactor `src/rtl_semantic_bridge.py` into thin wrapper
  that calls `ConfigurableERPipeline` with IC-specific YAML config.
- After C6: refactor `src/cross_repo_bridge.py` to delegate structural similarity.
- `community_detector.py` stays project-local (not ER duplicate resolution).

---

## 7) Calibration and Rollout Requirements

All new gates (A3/A4/A4b) follow the same rollout policy:

1. **Shadow mode**: compute gate outcomes, do not reject.
2. **Report-only mode**: include `gate_failures` in outputs/telemetry.
3. **Enforcement mode**: enable rejection with calibrated thresholds.

Before enforcement, produce calibration report:

- pass/fail counts by gate
- precision/recall/F1 impact vs baseline
- top false-positive and false-negative examples
- recommended default thresholds by dataset profile

Gate metrics must be compatible with the library's existing
`RuntimeQualityService` baseline framework.

---

## 8) Compatibility and Versioning

- `er_options_schema_version` already present in MCP responses — extend it.
- Additive changes only within a schema version.
- Breaking type/shape changes require:
  - schema version bump
  - migration note
  - MCP compatibility tests

---

## 9) Test and Quality Strategy

Each contribution includes:

1. **Unit tests (no DB)** for gate logic, alias handling, structural similarity.
2. **Integration tests (Docker ArangoDB)** for end-to-end matching behavior.
   Use the library's existing `conftest.py` auto-spin Docker pattern.
3. **Regression tests** with quality/performance budgets:
   - precision, recall, F1
   - candidate-pair volume
   - runtime + memory
   - gate rejection histograms
4. **Runtime baseline tests** compatible with `ci/` quality baselines.

---

## 10) Observability Requirements

Every new strategy/gate must emit:

- records processed, candidates generated
- accepted/rejected counts
- rejection reasons (`margin`, `token_overlap`, `type_affinity`, etc.)
- stage-level timing (`exact`, `embedding`, `jaccard`)
- resource estimates/actuals when available

These diagnostics should flow through:

- Python result objects (compatible with `RuntimeQualityService`)
- `explain_match` output
- MCP tool responses (or referenced artifacts)

---

## 11) Refactoring Plan for This Project

### B1. `src/rtl_semantic_bridge.py` → thin wrapper

**After:** C2 + C3a + C3b + C5 are available in the library.

Replace custom matching/gating/alias internals with library calls:

```python
from entity_resolution.core.configurable_pipeline import ConfigurableERPipeline

config = load_yaml("config/er_rtl_bridge.yaml")
pipeline = ConfigurableERPipeline(db, config)
results = pipeline.run(source_collection="RTL_Module", target_collection="OR1200_Golden_Entities")
```

Keep only:
- DB wiring and ArangoDB connection setup
- Profile-specific YAML defaults (`config/er_rtl_bridge.yaml`)
- Optional CLI ergonomics
- IC-specific post-processing (edge creation with `created_by` metadata)

### B2. `src/cross_repo_bridge.py` → partial wrapper

**After:** C6 (structural token-Jaccard) is available.

Delegate matching to library and retain only domain-specific lineage edge logic.

### B3. `src/local_graphrag/community_detector.py` → unchanged

Leiden community detection remains out of ER duplicate-resolution scope.

---

## 12) Appendix — Current Regression Reference Numbers

| Metric | Value | Notes |
|---|---|---|
| OR1200 exact matches | 93 | after stopword fix |
| OR1200 embedding matches | 8 | threshold 0.72 |
| MOR1KX exact matches | 4 | alias-driven |
| MOR1KX embedding matches | 51 | threshold 0.72 |
| MAROCCHINO exact matches | 12 | alias file + acronyms |
| IBEX exact matches | 30 | |
| IBEX embedding matches | 24 | |
| **Total RESOLVED_TO** | **193** | actual DB count 2026-03-25 |
| False positives removed | 8 | precision fix examples documented |
| Rejected threshold | 0.65 | retained as historical baseline only |

---

## 13) Appendix — Library Feature Matrix (v3.3.1 Assessment)

Summary of what exists in `arango-entity-resolution` v3.3.1 and what this plan adds.

| Feature | Library Status | Plan Action |
|---|---|---|
| Cross-collection matching | ✅ Shipped | Wire stages/gating when available |
| Configurable ER pipeline (YAML) | ✅ Shipped | Use as integration point |
| Golden record persistence | ✅ Shipped | — |
| Graph traversal blocking | ✅ Shipped | — |
| Vector/ANN blocking | ✅ Shipped | — |
| WCC clustering (multi-backend) | ✅ Shipped | — |
| LLM match verification | ✅ Shipped | Complement with gate diagnostics |
| IncrementalResolver | ✅ Shipped | Alias expansion must support it |
| Node2Vec embeddings | ✅ Shipped | — |
| MCP server (15+ tools) | ✅ Shipped | Extend with new options |
| Runtime quality baselines | ✅ Shipped | Align gate metrics |
| `explain_match` (basic) | ✅ Shipped | Extend with gate diagnostics (C4) |
| `TypeCompatibilityFilter` | ✅ Enrichment | Wire as pipeline gate (C3b) |
| `AcronymExpansionHandler` | ✅ Enrichment | Extend to multi-source (C5) |
| Multi-stage matching | ❌ Gap | **C2** |
| Score-margin gate | ❌ Gap | **C3a** |
| Token-overlap gate | ❌ Gap | **C3a** |
| Type-affinity gate (in pipeline) | ⚠️ Partial | **C3b** |
| Gate failure diagnostics | ❌ Gap | **C4** |
| Full alias expansion pipeline | ⚠️ Partial | **C5** |
| Structural token-Jaccard | ⚠️ Partial | **C6** |
| Temporal-aware ER | ❌ Not planned | Project-local concern |
| Hardware name normalization | ❌ Not planned | Project-local concern (custom transformer possible) |
| Community detection (Leiden) | ❌ Not planned | Project-local concern (B3) |
