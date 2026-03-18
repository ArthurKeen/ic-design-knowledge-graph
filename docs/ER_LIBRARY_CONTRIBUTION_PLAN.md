# Entity Resolution Library — Contribution Plan
_Drafted: 2026-03-16 | Revised: 2026-03-18 | Source: IC Knowledge Graph project learnings_

This document captures ER techniques proven in the IC Knowledge Graph project that
are worth contributing back to the `arango-entity-resolution` library once it
stabilises. It also describes the corresponding refactoring needed in this project
so it can consume those techniques from the library rather than re-implementing them.

---

## Background: What the IC Project Proved

The `RESOLVED_TO` semantic bridge (RTL nodes → Golden Entities) is fundamentally an
entity resolution task: given ~7,000 RTL port/signal records and ~600 golden
entities, find the best match for each RTL node with high precision. We ran three
full experimental cycles with a documented precision-first decision log. The key
findings are transferable.

---

## Part A — Contributions to the Library

### A1. Cross-Collection / Heterogeneous ER

**Gap:** The library's `resolve_entity` and `find_duplicates` operate within a
single collection. The most common production ER problem is *linking* records
across two collections with incompatible schemas (CRM leads → master accounts,
product catalog A → product catalog B, RTL ports → architecture entities).

**What we built:** `match_exact()` + `match_embedding()` in `src/rtl_semantic_bridge.py`
link `RTL_Port` / `RTL_Signal` records to `*_Golden_Entities` using a shared text
representation but completely different field names and cardinalities.

**Proposed API addition:**

```python
resolve_entity_cross_collection(
    source_collection:  str,          # "RTL_Port"
    target_collection:  str,          # "OR1200_Golden_Entities"
    source_text_field:  str | list,   # "expanded_name" with fallback to "name"
    target_text_fields: list[str],    # ["name", "aliases"]
    confidence_threshold: float = 0.80,
    top_k: int = 1,
    field_mapping: dict = None,       # optional schema bridge
    # --- GAP FIXES ---
    target_filter: dict = None,       # pre-filter target collection before matching
                                      # e.g. {"field": "type", "values": ["SIGNAL", "REGISTER"]}
                                      # replaces hardwired RTL_RELEVANT_TYPES
    source_skip_values: set = None,   # skip source records whose text field matches these values
                                      # e.g. {"clk", "rst", "a", "b"} — replaces SKIP_NAMES
) -> list[dict]                       # [{source_key, target_key, score, method}]
```

**`target_filter` rationale:** In the IC project, `RTL_RELEVANT_TYPES` is a
hardcoded set of 11 entity types that represent matchable architecture concepts.
Any collection with a categorical field (e.g. `type`, `category`, `label`)
would benefit from the same pre-filter. The parameter keeps the library agnostic
about what those values mean.

**`source_skip_values` rationale:** `SKIP_NAMES` (single-char port names like
`a`, `b`, `en`, plus infrastructure names `clk`, `rst`, `vcc`, `gnd`) should
never be matched — they are too generic to have meaningful counterparts. This is
a common pattern in any domain with short, infrastructure-level identifiers
(e.g. SQL column names, sensor IDs). The parameter makes it caller-supplied.

**Files to contribute:** `src/rtl_semantic_bridge.py` (stripped of IC-specific
logic), particularly `load_golden_entities()`, `load_rtl_nodes()`, and the
two-stage pipeline structure.

---

### A2. Multi-Stage Pipeline Strategy (`"exact_then_embedding"`)

**Gap:** `find_duplicates` uses one similarity pass. Running embedding on
everything is expensive and produces false positives for records that have an
obvious exact/alias match.

**What we built:** Stage 1 (exact/alias match, score=1.0) runs first;
Stage 2 (embedding cosine) only runs on the unmatched remainder. In practice this
reduced OR1200 embedding calls from 1,996 to 228 while keeping the same recall.

**Proposed API change** (additive, non-breaking):

```python
find_duplicates(
    collection: str,
    fields: list[str],
    strategy: str = "exact",   # existing values: "exact", "bm25"
                               # NEW: "multi_stage"
    stages: list[dict] = None, # only used when strategy="multi_stage"
    # e.g.:
    # stages=[
    #   {"type": "exact",     "fields": ["name", "aliases"], "score": 1.0},
    #   {"type": "embedding", "field": "description", "min_score": 0.72},
    # ]
)
```

Stage 2 receives only records not matched by Stage 1, so it is both faster and
more precise.

**Implementation note:** The existing `find_duplicates` blocking logic can be
re-used for Stage 1 with `strategy="exact"`. Stage 2 wraps the existing embedding
path. The plumbing is a loop over stages with an "already matched" exclusion set.

---

### A3. Score-Margin Gate

**Gap:** A single `confidence_threshold` cannot distinguish between a strong
unambiguous match (score=0.82, 2nd-best=0.51) and a noisy tie (score=0.74,
2nd-best=0.72). Both pass the threshold; only the first is trustworthy.

**What we built:** `_embedding_gate()` computes `margin = score - second_best`
and rejects matches where the lead is below a configurable threshold even if the
absolute score passes.

**Proposed API addition** (new optional parameter on `find_duplicates` and
`resolve_entity`):

```python
min_margin: float = 0.0   # 0 = disabled (current behaviour)
                           # 0.05 = require 5% lead over 2nd-best
```

**Implementation:** Requires the similarity computation to retain the top-2 scores
per candidate, which is a small change to the existing scoring loop.

---

### A4. Token-Overlap Acceptance Gate + Domain Stopwords

**Gap:** High embedding similarity without any shared lexical tokens is a strong
signal of a false positive in technical / domain-specific corpora. Generic words
("output", "counter", "memory") in golden entity names create noise in the word
index that drives spurious exact matches.

**What we built:**
- `_tokens()` — normalised token set from a text field.
- `WORD_INDEX_STOPWORDS` — domain-configurable set of words blocked from the
  word index (e.g. `{"output", "counter", "memory", "address", ...}`).
- Gate logic in `_embedding_gate()`: if token overlap is 0, require either a very
  high absolute score (>0.90) or a very high margin.

**Proposed API additions:**

```python
find_duplicates(
    ...
    require_token_overlap: bool = False,
    token_overlap_bypass_score: float = 0.92,   # skip gate if score > this
    word_index_stopwords: list[str] = None,      # domain-specific stopwords
)
```

These can default to their current (disabled) values so existing callers are
unaffected.

---

### A4b. Contextual Type-Affinity Gate

**Gap (newly identified):** The current `_embedding_gate()` in this project
contains two domain-hardwired checks that would leak IC-specific knowledge into
the library if contributed verbatim:

```python
# HARDWIRED — Wishbone bus is an IC-specific protocol
if rtl_has_wishbone and not golden_has_wishbone and score < 0.78:
    return False

# HARDWIRED — CLOCK_DOMAIN / HARDWARE_INTERFACE are IC-specific type names
if rtl_has_clk_rst and golden_type not in {"SIGNAL", "CLOCK_DOMAIN", "HARDWARE_INTERFACE"} ...
    return False
```

Both express the same generalizable intent: *"if the source record contains
tokens from a domain-specific context set, only accept a match whose target
belongs to a declared set of compatible types."* Neither the token sets nor the
type values should be hardcoded in the library.

**What needs generalizing:** Replace the hardwired checks with a user-supplied
`token_type_affinity` mapping.

**Proposed API addition** (new optional parameter on `resolve_entity_cross_collection`
and `find_duplicates`):

```python
token_type_affinity: dict[str, dict] = None
# Maps a frozenset of source tokens → allowed target types + bypass score.
# e.g.:
# token_type_affinity = {
#   "wishbone wb":                {"allowed_types": ["HARDWARE_INTERFACE", "BUS_PROTOCOL"],
#                                  "bypass_score": 0.78},
#   "clk clock rst reset":        {"allowed_types": ["SIGNAL", "CLOCK_DOMAIN"],
#                                  "bypass_score": 0.78},
# }
#
# Semantics:
#   If source_tokens ∩ key_tokens is non-empty AND target["type"] not in allowed_types
#   AND score < bypass_score → reject the candidate.
#   Keys are whitespace-separated token strings for human readability.
```

**Implementation contract:**
- Keys are parsed at call time (split on whitespace → frozenset).
- `target_type_field` (default `"type"`) specifies which field on the target
  record holds the type value; the library never assumes a field name.
- If `token_type_affinity` is `None` (default), the gate is a no-op and
  existing behaviour is preserved.
- Gate failures are recorded in the `gate_failures` list (see A5) for
  auditability.

**IC project refactoring:** The two hardwired `if` blocks in `_embedding_gate()`
are replaced by a single `_apply_type_affinity_gate()` library call, and the
affinity map is declared in the `rtl_semantic_bridge.py` CLI config section:

```python
RTL_TYPE_AFFINITY = {
    "wishbone wb":         {"allowed_types": ["HARDWARE_INTERFACE", "BUS_PROTOCOL"],
                            "bypass_score": 0.78},
    "clk clock rst reset": {"allowed_types": ["SIGNAL", "CLOCK_DOMAIN", "HARDWARE_INTERFACE"],
                            "bypass_score": 0.78},
}
```

This pattern is directly analogous to type-constrained entity linking in NLP
(e.g. "only link a PERSON mention to a PERSON entity, not an ORG").

---

### A5. `explain_match` Enhancement: Gate Failure Reasons

**Gap:** `explain_match` currently shows *why* two records match (positive signal).
It cannot explain *why a high-scoring candidate was rejected* by precision gates,
making false-positive audits manual and opaque.

**What we built:** Each call to `_embedding_gate()` produces a structured set of
gate outcomes that are recorded on the match candidate:
```python
{
    "score":         0.74,
    "second_best":   0.72,
    "margin":        0.02,
    "token_overlap": 0,
    "accepted":      False,
    "gate_failures": ["margin=0.02 < min_margin=0.05",
                      "token_overlap=0 with score=0.74 < bypass=0.92"],
}
```

**Proposed change to `explain_match`:** Add a `gates` section to the output.
The section now includes all gate types from A3, A4, and A4b:

```json
{
  "score": 0.74,
  "accepted": false,
  "field_scores": {"name": 0.61, "description": 0.81},
  "gates": {
    "margin":        {"value": 0.02, "threshold": 0.05, "passed": false},
    "token_overlap": {"value": 0, "bypass_score": 0.92, "passed": false},
    "type_affinity": {
      "triggered_by": ["wb", "wishbone"],
      "target_type":  "REGISTER",
      "allowed_types": ["HARDWARE_INTERFACE", "BUS_PROTOCOL"],
      "bypass_score": 0.78,
      "passed": false
    }
  }
}
```

This is high-leverage: it turns `explain_match` from a "why do they match" tool
into a "why was this rejected" debugging tool.

---

### A6. Alias / Synonym Expansion Before Blocking

**Gap:** The library matches on field values as-is. Domain entities frequently
have official names, abbreviations, and derived acronyms that all refer to the
same concept ("Development Interface" / "di" / "DI"). Without expansion,
obvious matches are missed at the exact-match stage and have to be recovered by
slower, less precise embedding.

**What we built:** Three alias sources, applied before blocking:
1. `field` — use an existing `aliases` field on the record.
2. `file` — load curated overrides from `rtl_semantic_aliases.json`.
3. `acronym` — auto-generate initial-letter acronyms from multi-word names.

**Proposed API addition:**

```python
find_duplicates(
    ...
    alias_sources: list[dict] = None,
    # e.g.:
    # alias_sources=[
    #   {"type": "field",   "field": "aliases"},
    #   {"type": "file",    "path":  "entity_aliases.json"},
    #   {"type": "acronym", "auto":  True, "min_word_len": 4},
    # ]
)
```

The alias expansion runs as a pre-processing step; expanded aliases are added to
the blocking index but not stored back on the source record.

**Caution:** Auto-acronym expansion must respect a minimum word length to avoid
generating noise (e.g. "Development Interface" → "di" is useful; "of" → "o" is
not). The `min_word_len` parameter controls this.

---

### A7. Structural Token-Jaccard Similarity Type

**Gap:** For entities without descriptive text (e.g. hardware modules described
only by their port list), embedding similarity is meaningless. Token Jaccard on
structured attributes (port names, tag lists) provides a reliable structural
signal.

**What we built:** `_port_signature_similarity()` and `_label_similarity()` in
`src/cross_repo_bridge.py`:
```
score = 0.6 * jaccard(tokens_a, tokens_b) + 0.4 * (1 - size_diff_ratio)
```

**Proposed API addition** (new `similarity_type` option):

```python
find_duplicates(
    ...
    similarity_type: str = "embedding",  # existing
    # NEW: "token_jaccard" — for structured list fields
    token_jaccard_field: str = None,     # field containing list of strings
)
```

This is particularly useful for schema-heavy domains (hardware, genomics,
e-commerce product attributes) where text descriptions are absent or unreliable.

---

## Part B — Refactoring Plan for This Project

Once the library ships the above capabilities, the following source files can be
simplified:

### B1. `src/rtl_semantic_bridge.py` → thin wrapper

| Current code | Replaced by |
|---|---|
| `_normalise()`, `_tokens()` | library internals |
| `match_exact()` | `resolve_entity_cross_collection(..., strategy="exact")` |
| `match_embedding()` + `_embedding_gate()` | `resolve_entity_cross_collection(..., strategy="multi_stage", stages=[...])` |
| `WORD_INDEX_STOPWORDS` | `word_index_stopwords=` parameter (A4) |
| `_load_alias_overrides()` + alias merge | `alias_sources=[{"type":"file", ...}]` (A6) |
| `load_golden_entities()` auto-acronym | `alias_sources=[{"type":"acronym", ...}]` (A6) |
| `RTL_RELEVANT_TYPES` set | `target_filter={"field":"type","values":[...]}` (A1) |
| `SKIP_NAMES` set | `source_skip_values={...}` (A1) |
| Wishbone/clk hardwired `if` blocks | `token_type_affinity=RTL_TYPE_AFFINITY` (A4b) |

The file shrinks from ~620 lines to ~120 (DB connection, config, affinity map declaration, CLI wrapper).

### B2. `src/cross_repo_bridge.py` → partial wrapper

| Current code | Replaced by |
|---|---|
| `_port_signature_similarity()` | library `similarity_type="token_jaccard"` |
| `_label_similarity()` | library `similarity_type="token_jaccard"` |
| `build_embedding_bridges()` | `find_duplicates(..., strategy="embedding")` |
| `build_structural_bridges()` | `find_duplicates(..., strategy="token_jaccard")` |

`build_lineage_edges()` (rule-based `CROSS_REPO_EVOLVED_FROM`) stays in this
project — it is domain-specific.

### B3. `src/local_graphrag/community_detector.py` → stays

Leiden community detection is conceptually distinct from ER (it groups related
entities, not duplicate ones). Keep in this project; potentially contribute as a
separate `arango-community-detection` module.

---

## Part C — Sequencing

Each PR has two deliverables: a **library change** and a **MCP server change**.
The MCP server (`src/entity_resolution/mcp/server.py`) is a thin wrapper — new
library params are invisible to AI agents until the MCP signatures are updated.

| PR | Library | MCP server update |
|---|---|---|
| **C1** | `resolve_entity_cross_collection()` + `target_filter` + `source_skip_values` | **New tool**: `resolve_entity_cross_collection` |
| **C2** | `find_duplicates` + `stages` param | Add `stages: list` to `find_duplicates` tool |
| **C3** | `min_margin`, `require_token_overlap`, `word_index_stopwords`, `token_type_affinity`, `target_type_field` | Add all five to `find_duplicates` + `resolve_entity` tools |
| **C4** | `explain_match` output gains `gates` section | Docstring update only — output enrichment flows through automatically |
| **C5** | `alias_sources` param | Add `alias_sources: list` to `find_duplicates` + `resolve_entity` tools |
| **C6** | `similarity_type="token_jaccard"`, `token_jaccard_field` | Add both to `find_duplicates` tool |

```
     ├── C1: Ship A1 (cross-collection resolve_entity)       ← highest value, self-contained
     │         includes: target_filter, source_skip_values   ← closes RTL_RELEVANT_TYPES / SKIP_NAMES gaps
     │         MCP: new resolve_entity_cross_collection tool
     ├── C2: Ship A2 (multi_stage strategy)                  ← depends on A1 scaffolding
     │         MCP: stages param on find_duplicates
     ├── C3: Ship A3 + A4 + A4b (margin + overlap + type-   ← all three gates travel together;
     │         affinity gates)                                  A4b closes contextual hardwiring gap
     │         MCP: 5 new params on find_duplicates + resolve_entity
     ├── C4: Ship A5 (explain_match gate failures)           ← UX, depends on A3/A4/A4b
     │         MCP: docstring + output format update only
     ├── C5: Ship A6 (alias expansion)                       ← more invasive, separate PR
     │         MCP: alias_sources param on find_duplicates + resolve_entity
     └── C6: Ship A7 (token_jaccard similarity)              ← additive, separate PR
               MCP: similarity_type + token_jaccard_field on find_duplicates

This project refactoring:
     │
     ├── After C1+C2+C3: refactor rtl_semantic_bridge.py (B1)
     │     replaces: SKIP_NAMES, RTL_RELEVANT_TYPES, _embedding_gate() hardwiring
     ├── After C6:       refactor cross_repo_bridge.py (B2)
     └── Never:          community_detector.py (stays here)
```

---

## Part D — Test Strategy for Library Contributions

Each contribution should be accompanied by:

1. **Unit tests** (pure Python, no DB): test the gate logic, alias expansion,
   token Jaccard in isolation. Mirror the pattern in `tests/test_bridging.py`.
2. **Integration test** (real ArangoDB, Docker): mirror `tests/conftest.py` —
   spin up a throwaway container, run `find_duplicates` against seeded data,
   assert counts and precision metrics.
3. **Regression test**: the OR1200 `RESOLVED_TO` frozen counts (101 exact, 8
   embedding) serve as a precision/recall baseline. Any library change that shifts
   these counts by >5% needs a documented justification.

The `tests/test_e2e_local.py` Docker fixture in this project can be extracted into
a shared test utility that both projects import.

---

## Appendix — Key Numbers for Regression

| Metric | Value | Notes |
|---|---|---|
| OR1200 exact matches | 93 | after WORD_INDEX_STOPWORDS fix |
| OR1200 embedding matches | 8 | at 0.72 threshold |
| MOR1KX exact matches | 4 | alias-driven |
| MOR1KX embedding matches | 51 | at 0.72 threshold |
| MAROCCHINO exact matches | 12 | alias file + acronyms |
| IBEX exact matches | 30 | |
| IBEX embedding matches | 24 | |
| **Total RESOLVED_TO** | **222** | frozen 2026-03-16 |
| False positives removed | 8 | Q→dbg_bp_o, cnt→PC, mem→MemCtrl, … |
| Rejected threshold | 0.65 | "coin toss" — documented non-decision |
