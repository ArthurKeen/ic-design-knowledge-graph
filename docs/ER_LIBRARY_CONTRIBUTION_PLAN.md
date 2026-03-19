# Entity Resolution Library — Contribution Plan (Revised)
_Drafted: 2026-03-16 | Revised: 2026-03-18 | Revised again: 2026-03-18_

This document captures entity-resolution techniques proven in the IC Knowledge Graph
project and defines how to contribute them to `arango-entity-resolution` safely,
with stable APIs, explicit rollout controls, and measurable quality/performance gates.

---

## 1) Background: What the IC Project Proved

The `RESOLVED_TO` semantic bridge (RTL nodes -> golden entities) is an ER task:
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

## 2) Design Principles for Contributions

1. **Neutral by default:** no IC-specific token sets, type names, or stopwords.
2. **Stable API shape:** avoid growing top-level params on core methods/tool signatures.
3. **Calibrated gates:** no new precision gate should be enabled without dataset calibration.
4. **Observable behavior:** all acceptance/rejection gates emit diagnostics.
5. **Safe rollout:** introduce features in shadow/report-only mode before enforcement.
6. **MCP parity:** every library capability must be reflected in MCP tool contracts.

---

## 3) API Strategy (Important Update)

To avoid brittle signatures, new controls are grouped into option objects.
Top-level APIs stay compact and backwards compatible.

### 3.1 Updated shape for `find_duplicates`

```python
find_duplicates(
    collection: str,
    fields: list[str],
    strategy: str = "exact",  # existing
    options: dict | None = None,
)
```

`options` carries additive capability blocks:

```python
options = {
    "stages": [...],                 # multi-stage pipeline
    "gating": {...},                 # margin/overlap/type-affinity
    "aliasing": {...},               # alias sources
    "similarity": {...},             # token_jaccard and others
    "execution": {...},              # limits, timeout, batch/chunk sizing
    "diagnostics": {"level": "full"} # gate and scoring telemetry
}
```

### 3.2 New API for cross-collection linking

```python
resolve_entity_cross_collection(
    source_collection: str,
    target_collection: str,
    source_fields: list[str],
    target_fields: list[str],
    options: dict | None = None,
) -> list[dict]
```

`options` MUST support:

- `field_mapping`
- `target_filter`
- `source_skip_values`
- `candidate_limit`
- `batch_size`
- `max_runtime_ms`
- `deterministic_tiebreak`
- `return_diagnostics`

This keeps performance and safety controls explicit for large target collections.

---

## 4) Contribution Scope (Library)

### A1. Cross-Collection / Heterogeneous ER

**Goal:** Link records across two collections with incompatible schemas.

**Contribution:** `resolve_entity_cross_collection(...)` with generic filtering,
skip lists, and execution controls.

**Generalized IC learnings mapped in options:**

- `target_filter` replaces hardcoded relevant-type sets.
- `source_skip_values` replaces hardcoded generic name suppression.

---

### A2. Multi-Stage Pipeline Strategy (`exact_then_embedding`)

**Goal:** Run cheap/high-precision stages first and only escalate unmatched records.

**Contribution:** stage configuration under `options["stages"]`:

```python
"stages": [
  {"type": "exact", "fields": ["name", "aliases"], "score": 1.0},
  {"type": "embedding", "field": "description", "min_score": 0.72}
]
```

---

### A3. Score-Margin Gate

**Goal:** reject ties/noisy near-ties even when absolute score passes.

**Contribution:** `options["gating"]["min_margin"]` (default disabled).

---

### A4. Token-Overlap Gate + Domain Stopwords

**Goal:** reduce semantic false positives where lexical grounding is absent.

**Contribution:**

- `options["gating"]["require_token_overlap"]`
- `options["gating"]["token_overlap_bypass_score"]`
- `options["gating"]["word_index_stopwords"]`

Default behavior remains unchanged unless enabled.

---

### A4b. Contextual Type-Affinity Gate

**Goal:** enforce soft type compatibility based on source-token context.

**Contribution:**

- `options["gating"]["token_type_affinity"]`
- `options["gating"]["target_type_field"]` (default `"type"`)

No domain values are hardcoded in library code.

---

### A5. `explain_match` Enhancement: Gate Failures

**Goal:** explain why high-scoring candidates were rejected.

**Contribution:** output `gates` diagnostics section with pass/fail by gate type
and human-readable reasons (`gate_failures`).

---

### A6. Alias / Synonym Expansion Before Blocking

**Goal:** improve exact-stage recall for abbreviations/acronyms/synonyms.

**Contribution:** `options["aliasing"]` with secure source model:

```python
"aliasing": {
  "sources": [
    {"type": "field", "field": "aliases"},
    {"type": "managed_ref", "ref": "entity_aliases_v1"},  # preferred in server mode
    {"type": "inline", "map": {...}},
    {"type": "acronym", "auto": True, "min_word_len": 4}
  ]
}
```

**Security note:** arbitrary filesystem paths are disallowed in MCP/server mode.

---

### A7. Structural Token-Jaccard Similarity

**Goal:** provide robust matching where descriptive text is sparse or absent.

**Contribution:** `options["similarity"]` support for:

- `type: "token_jaccard"`
- field config for structured token/list features

---

## 5) MCP Contract Updates (Required)

Each library PR must include matching MCP signature updates so agents can use the
new capabilities immediately.

Additions must remain backward compatible by using nested option objects instead of
new top-level parameters whenever possible.

---

## 6) Sequencing (Revised)

### C1 — Cross-collection linking foundation

- Library: A1
- MCP: new `resolve_entity_cross_collection` tool
- Acceptance: deterministic output and execution guardrails (`candidate_limit`,
  `max_runtime_ms`) in place

### C2 — Multi-stage pipeline

- Library: A2
- MCP: `find_duplicates` accepts `options.stages`

### C3a — Core precision gates

- Library: A3 + A4
- MCP: `options.gating.{min_margin,require_token_overlap,token_overlap_bypass_score,word_index_stopwords}`

### C3b — Contextual type affinity

- Library: A4b
- MCP: `options.gating.{token_type_affinity,target_type_field}`

### C4 — Explainability enrichment

- Library: A5
- MCP: `explain_match` response schema/documentation update

### C5 — Alias expansion

- Library: A6
- MCP: `options.aliasing`

### C6 — Structural token-jaccard

- Library: A7
- MCP: `options.similarity`

### Project refactor dependencies

- After C1 + C2 + C3a + C3b: refactor `src/rtl_semantic_bridge.py` into thin wrapper.
- After C6: refactor `src/cross_repo_bridge.py` to delegate structural similarity.
- `community_detector.py` stays project-local (not ER duplicate resolution).

---

## 7) Calibration and Rollout Requirements (New)

All new gates (A3/A4/A4b) follow the same rollout policy:

1. **Shadow mode**: compute gate outcomes, do not reject.
2. **Report-only mode**: include gate_failures in outputs/telemetry.
3. **Enforcement mode**: enable rejection with calibrated thresholds.

Before enforcement, produce calibration report:

- pass/fail counts by gate
- precision/recall/F1 impact vs baseline
- top false-positive and false-negative examples
- recommended default thresholds by dataset profile

---

## 8) Compatibility and Versioning (New)

- Add `er_options_schema_version` to exported configs and MCP responses where relevant.
- Additive changes only within a schema version.
- Breaking type/shape changes require:
  - schema version bump
  - migration note
  - MCP compatibility tests

---

## 9) Test and Quality Strategy (Updated)

Each contribution includes:

1. **Unit tests (no DB)** for gate logic, alias handling, structural similarity.
2. **Integration tests (Docker ArangoDB)** for end-to-end matching behavior.
3. **Regression tests** with quality/performance budgets:
   - precision, recall, F1
   - candidate-pair volume
   - runtime + memory
   - gate rejection histograms

Frozen counts remain a reference signal, but pass/fail is based on metric budgets,
not counts alone.

---

## 10) Observability Requirements (New)

Every new strategy/gate must emit:

- records processed, candidates generated
- accepted/rejected counts
- rejection reasons (`margin`, `token_overlap`, `type_affinity`, etc.)
- stage-level timing (`exact`, `embedding`, `jaccard`)
- resource estimates/actuals when available

These diagnostics should flow through:

- Python result objects
- `explain_match` output
- MCP tool responses (or referenced artifacts)

---

## 11) Refactoring Plan for This Project

### B1. `src/rtl_semantic_bridge.py` -> thin wrapper

Replace custom matching/gating/alias internals with library calls plus local config.
Keep only:

- DB wiring
- profile-specific defaults
- optional CLI ergonomics

### B2. `src/cross_repo_bridge.py` -> partial wrapper

Delegate matching to library (`embedding`, `token_jaccard`) and retain only
domain-specific lineage edge logic.

### B3. `src/local_graphrag/community_detector.py` -> unchanged

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
| **Total RESOLVED_TO** | **222** | frozen 2026-03-16 |
| False positives removed | 8 | precision fix examples documented |
| Rejected threshold | 0.65 | retained as historical baseline only |
