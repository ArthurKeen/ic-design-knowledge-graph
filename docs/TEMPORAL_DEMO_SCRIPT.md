# Temporal IC Knowledge Graph — Demo Script
## "Déjà Vu of Design: 30 Years of Open-Source Processor Evolution"

**Database:** `ic-knowledge-graph-temporal`  
**ArangoDB UI:** https://5ieeavs2.rnd.pilot.arango.ai  
**Estimated runtime:** 20–30 minutes  
**Audience:** Technical stakeholders, hardware engineers, EDA researchers

---

## Setup — Before You Present

1. Open the ArangoDB Web UI and **switch to database `ic-knowledge-graph-temporal`** (top-left dropdown)
2. Open **Queries** (left nav → Queries icon)
3. Keep this script open in a second window; paste each query when ready

**What's in the DB:**

| Item | Count |
|---|---|
| Repositories ingested | 4 (OR1200, mor1kx, marocchino, ibex) |
| Total commits | 3,808 |
| RTL modules (across all history) | 6,594 |
| Named design epochs | 390 |
| Design situations | 723 |
| GraphRAG entities | 317 |
| Cross-repo bridges | 34 |

---

## Scene 1 — "The Living Graph" (~3 min)

**Talking point:** *Traditional graphs capture a snapshot. This graph captures 30 years of evolution. Every RTL module exists in time — it has a birthday and sometimes a death date.*

### Query 1a — Show the scope
```aql
// How much history do we have?
LET repos = (
  FOR c IN GitCommit
    COLLECT r = c.repo WITH COUNT INTO n
    RETURN {repo: r, commits: n}
)
LET epochs = (FOR e IN DesignEpoch COLLECT r = e.repo WITH COUNT INTO n RETURN {repo: r, epochs: n})
RETURN {
  total_commits:  SUM(repos[*].commits),
  total_modules:  LENGTH(RTL_Module),
  total_epochs:   LENGTH(DesignEpoch),
  total_situations: LENGTH(DesignSituation),
  by_repo: repos
}
```

**Expected output:** 3808 commits, 6594 modules, 390 epochs, 723 situations.

### Query 1b — Show the timeline (graph viewer friendly)
```aql
// The epoch timeline for mor1kx — shows milestone tags + time periods
FOR e IN DesignEpoch
  FILTER e.repo == "openrisc/mor1kx.git"
  SORT e.start_ts ASC
  RETURN {
    epoch:      e.label,
    type:       e.epoch_type,
    start_date: DATE_FORMAT(e.start_ts * 1000, "%yyyy-%mm-%dd"),
    git_tag:    e.git_tag
  }
```

**Point out:** Milestone tags like `v5.2` are automatically detected from git. Time-period epochs (`period_2013_09`) fill the gaps.

---

## Scene 2 — "The Time Machine" (~4 min)

**Talking point:** *We can ask: "What did OR1200 look like in 2001, before the MMU was added?" Or: "How many ibex modules existed when the project started vs. today?"*

### Query 2a — State of OR1200 at its very beginning (2001)

```aql
// What RTL modules existed in OR1200 at the beginning of the project?
LET target_ts = DATE_TIMESTAMP("2001-11-01") / 1000  // Nov 2001
FOR m IN RTL_Module
  FILTER m.repo == "openrisc/or1200.git"
  FILTER m.valid_from_ts <= target_ts
  FILTER m.valid_to_ts > target_ts
  SORT m.label ASC
  RETURN {
    module: m.label,
    epoch:  m.design_epoch,
    file:   m.file
  }
```

### Query 2b — Show ibex module growth over time

```aql
// How did ibex grow? Count distinct modules per epoch
FOR e IN DesignEpoch
  FILTER e.repo == "lowRISC/ibex.git"
  LET module_count = LENGTH(
    FOR m IN RTL_Module
      FILTER m.repo == "lowRISC/ibex.git"
      FILTER m.valid_from_ts <= (e.end_ts != null ? e.end_ts : 9999999999)
      FILTER m.valid_to_ts > e.start_ts
      RETURN 1
  )
  FILTER module_count > 0
  SORT e.start_ts ASC
  LIMIT 15
  RETURN {
    epoch:    e.label,
    date:     DATE_FORMAT(e.start_ts * 1000, "%yyyy-%mm"),
    modules:  module_count
  }
```

**Point out:** ibex started with ~10 modules in 2016 and grew to 30+ through 268 named epochs.

---

## Scene 3 — "Design Situations — The Déjà Vu Index" (~5 min)

**Talking point:** *We automatically classify every important design moment across all repos. When a new subsystem gets added, when a major refactor happens, when a release is prepared — these are indexed as "Design Situations" that can be matched against future work.*

### Query 3a — Show the situation inventory

```aql
// What kinds of design situations exist across all repos?
FOR s IN DesignSituation
  COLLECT class = s.situation_class, repo = s.repo WITH COUNT INTO n
  SORT repo, class
  RETURN {situation_class: class, repo: repo, count: n}
```

### Query 3b — Show a major refactor situation with its modules

```aql
// Pick a dramatic refactor situation in ibex and show what changed
FOR s IN DesignSituation
  FILTER s.repo == "lowRISC/ibex.git"
  FILTER s.situation_class == "major_refactor"
  SORT s.valid_from_ts ASC
  LIMIT 1
  LET affected_modules = (
    FOR m IN RTL_Module
      FILTER m.repo == s.repo
      FILTER m.design_epoch == s.epoch
      RETURN m.label
  )
  RETURN {
    situation:    s.label,
    epoch:        s.epoch,
    date_range:   DATE_FORMAT(s.valid_from_ts * 1000, "%yyyy-%mm-%dd"),
    tags:         s.tags,
    modules_in_epoch: LENGTH(affected_modules),
    sample_modules: affected_modules[0..4]
  }
```

### Query 3c — Release preparation situations (milestone epochs)

```aql
// All release_prep situations — the moments before each release
FOR s IN DesignSituation
  FILTER s.situation_class == "release_prep"
  SORT s.valid_from_ts ASC
  RETURN {
    repo:    s.repo,
    release: s.epoch,
    date:    DATE_FORMAT(s.valid_from_ts * 1000, "%yyyy-%mm-%dd"),
    outcome: s.outcome,
    tags:    s.tags
  }
```

**Point out:** Every git release tag becomes a `release_prep` situation — automatically, without any manual annotation.

---

## Scene 4 — "Cross-Repo Bridges — Structural DNA" (~5 min)

**Talking point:** *Even though OR1200 was written in 2001 and ibex was written in 2016, they share structural patterns. Here we can see which modules are architecturally equivalent across the lineage.*

### Query 4a — Show all structural bridges
```aql
// All cross-repo structural connections
FOR e IN CROSS_REPO_SIMILAR_TO
  LET src = DOCUMENT(e._from)
  LET tgt = DOCUMENT(e._to)
  FILTER src != null AND tgt != null
  SORT e.similarity_score DESC
  RETURN {
    from_module: src.label,
    from_repo:   src.repo,
    to_module:   tgt.label,
    to_repo:     tgt.repo,
    score:       e.similarity_score,
    type:        e.similarity_type
  }
```

**Point out:** Modules like `cpu`, `alu`, `ctrl`, `if_stage` appear across OR1200, mor1kx, and ibex — showing the structural DNA that flows through the OpenRISC lineage into RISC-V.

### Query 4b — Trace the lineage chain (EVOLVED_FROM)
```aql
// The architectural lineage edge — which repo evolved from which?
FOR e IN CROSS_REPO_EVOLVED_FROM
  LET src = DOCUMENT(e._from)
  LET tgt = DOCUMENT(e._to)
  RETURN {
    evolved:     src.repo,
    derived_from: tgt.repo,
    evidence:    e.lineage_type,
    score:       e.similarity_score
  }
```

**Point out:** marocchino `evolved_from` mor1kx — confirmed by both structural label matching AND embedding similarity of their documentation entities.

### Query 4c — Cross-repo entity concepts (GraphRAG)
```aql
// What concepts appear in multiple repos' documentation?
FOR e IN OR1200_Golden_Entities
  LET matches = (
    FOR e2 IN MOR1KX_Golden_Entities
      FILTER LOWER(e2.entity_name) == LOWER(e.entity_name)
      RETURN e2.entity_name
  )
  FILTER LENGTH(matches) > 0
  RETURN {
    concept:    e.entity_name,
    type:       e.entity_type,
    in_or1200:  true,
    in_mor1kx:  true
  }
```

---

## Scene 5 — "The Déjà Vu Query — It's Happened Before" (~5 min)

**Talking point:** *Now for the showpiece: a current engineer is adding a fetch stage to their pipeline. The system instantly recognizes this situation has occurred before — in three different projects — and surfaces what happened next.*

### Query 5a — Find all situations where a fetch-related module was introduced
```aql
// Has anyone added a fetch module before? When and in which project?
FOR s IN DesignSituation
  FILTER s.situation_class == "subsystem_addition"
  FILTER LENGTH(
    FOR t IN s.tags
      FILTER CONTAINS(LOWER(t), "fetch") OR CONTAINS(LOWER(t), "if_")
      RETURN 1
  ) > 0
  SORT s.valid_from_ts ASC
  RETURN {
    repo:    s.repo,
    epoch:   s.epoch,
    date:    DATE_FORMAT(s.valid_from_ts * 1000, "%yyyy-%mm-%dd"),
    modules: s.tags,
    outcome: s.outcome
  }
```

### Query 5b — The full Déjà Vu traversal: commit → module → epoch → situation → docs
```aql
// Full chain: a specific module → its epoch → situation → related doc entities
LET target_module = FIRST(
  FOR m IN RTL_Module
    FILTER m.repo == "openrisc/or1200.git" AND CONTAINS(m.label, "if_fetch")
    LIMIT 1 RETURN m
)

// If no if_fetch, use a prominent module
LET module = target_module != null ? target_module : FIRST(
  FOR m IN RTL_Module
    FILTER m.repo == "openrisc/or1200.git"
    SORT m.valid_from_ts ASC
    LIMIT 1 RETURN m
)

LET epoch = FIRST(FOR e IN DesignEpoch FILTER e.repo == module.repo AND e._key == FIRST(
  FOR be IN BELONGS_TO_EPOCH FILTER be._from == module._id RETURN PARSE_IDENTIFIER(be._to).key
) RETURN e)

LET situation = FIRST(
  FOR s IN DesignSituation
    FILTER s.repo == module.repo AND s.epoch == module.design_epoch
    LIMIT 1 RETURN s
)

LET doc_entities = (
  FOR e IN OR1200_Golden_Entities
    FILTER CONTAINS(LOWER(e.entity_name), SPLIT(module.label, "_")[-1])
    LIMIT 3
    RETURN e.entity_name
)

RETURN {
  module:      module.label,
  epoch:       module.design_epoch,
  situation:   situation.situation_class,
  situation_tags: situation.tags,
  related_docs: doc_entities,
  what_happened_next: situation.outcome
}
```

---

## Scene 6 — "Graph Visualization" (~4 min)

**Talking point:** *Let me show you this in the graph viewer — you can see the temporal structure visually.*

### In the ArangoDB Graph Viewer:

1. Navigate to **Graphs** → `IC_Temporal_Knowledge_Graph`
2. **Start node:** enter `DesignEpoch/` + any key from this query:
   ```aql
   FOR e IN DesignEpoch
     FILTER e.repo == "openrisc/mor1kx.git" AND e.epoch_type == "milestone_tag"
     LIMIT 1 RETURN e._id
   ```
3. Set **depth = 2**, layout = **hierarchical**
4. You'll see: `DesignEpoch` → `BELONGS_TO_EPOCH` → `RTL_Module` nodes
5. Click on an `RTL_Module` to expand → shows `MODIFIED` edges → `GitCommit` nodes

**Colour coding to mention:**
- Purple nodes = `DesignEpoch`
- Blue/green nodes = `RTL_Module` (darker = older in history)
- Teal = `DesignSituation`
- Gold dashed edges = `CROSS_REPO_SIMILAR_TO`

### Cross-repo view:
```aql
// Visualize the cross-repo bridges as a subgraph
// (copy this ID into the graph viewer start node)
FOR e IN CROSS_REPO_SIMILAR_TO LIMIT 1 RETURN e._from
```
Then expand 2 hops — you'll see two modules from different repos connected by the gold `CROSS_REPO_SIMILAR_TO` edge.

---

## Q&A Prep — Likely Questions

| Question | Answer |
|---|---|
| "How long did ETL take?" | ibex: ~2 hours for 2908 commits. OR1200 (48 commits): ~5 min. Fully idempotent — re-run skips already-ingested commits |
| "How are epochs determined?" | Four rules in priority order: (1) first commit, (2) git release tags, (3) 180-day time windows, (4) >15% RTL file change rate |
| "Can this work on proprietary repos?" | Yes — just needs git clone access. No cloud calls during ETL. GraphRAG entity extraction requires OpenAI or Ollama |
| "What's the ArangoDB query latency?" | Single-repo temporal queries: <200ms. Cross-repo traversals: <2s. GraphRAG community lookups: <100ms |
| "Can I query by author or spec section?" | Yes for author (via `GitCommit.metadata.author`). Spec-to-code links require the `RESOLVED_TO` bridge — next step via full consolidator run |
| "What about proprietary Verilog formats?" | Parser handles synthesizable SystemVerilog subset. VHDL not yet supported — planned for Phase 3 extension |
| "How many more repos can you add?" | Schema is unbounded. Each new repo adds its prefix namespace. We've tested at 4 repos / 3808 commits; ArangoDB Community handles millions |

---

## Cleanup Query (DB Sanity Check)

Run this before the demo to confirm the DB is healthy:

```aql
RETURN {
  GitCommit:         LENGTH(GitCommit),
  RTL_Module:        LENGTH(RTL_Module),
  DesignEpoch:       LENGTH(DesignEpoch),
  DesignSituation:   LENGTH(DesignSituation),
  BELONGS_TO_EPOCH:  LENGTH(BELONGS_TO_EPOCH),
  CROSS_REPO_SIMILAR_TO:    LENGTH(CROSS_REPO_SIMILAR_TO),
  CROSS_REPO_EVOLVED_FROM:  LENGTH(CROSS_REPO_EVOLVED_FROM),
  OR1200_entities:   LENGTH(OR1200_Entities),
  MOR1KX_entities:   LENGTH(MOR1KX_Entities),
  IBEX_entities:     LENGTH(IBEX_Entities),
  MAROCCHINO_entities: LENGTH(MAROCCHINO_Entities)
}
```

**Healthy expected values:**
- GitCommit: 3808, RTL_Module: 6594, DesignEpoch: ~390, DesignSituation: ~723
- BELONGS_TO_EPOCH: ~10200, CROSS_REPO_SIMILAR_TO: ~33
- OR1200_entities: 157, MOR1KX_entities: 38, IBEX_entities: 67, MAROCCHINO_entities: 55
