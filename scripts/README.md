# Scripts Directory

Utility scripts for setup, maintenance, ingestion, and debugging of the Integrated Circuit (IC) Temporal Knowledge Graph (`IC_Temporal_Knowledge_Graph` in ArangoDB).

---

## Directory Structure

```
scripts/
├── README.md              This file
├── rebuild_database.sh    Full rebuild pipeline (ingestion → graph → visualizer)
├── master_etl.py          Legacy single-repo ETL orchestrator
├── smoke_test.py          ArangoDB connectivity smoke test
├── customer_workflow.py   Numbered exercise database workflow driver
├── diagnose_graphrag.py   GraphRAG import diagnostics
├── validate_er_migration.py   ER library import validation
├── migrate_collections.py     Copy collections between databases (env-driven)
├── list_bridging_examples.py  List RESOLVED_TO bridging demo examples
├── local_er_mcp.sh        Local Entity Resolution MCP launcher (developer)
├── multi_repo/            Multi-repo ingestion (registry-driven)
│   ├── ingest_repo.py
│   ├── clone_manager.py
│   ├── run_all_repos.sh
│   └── repo_registry.yaml
├── temporal/              Temporal ETL helpers (single-repo / JSONL load)
│   ├── create_temporal_graph.py
│   ├── load_temporal_data.py
│   └── run_temporal_etl.sh
├── setup/                 Visualizer installers, DB helpers, patches
│   ├── install_ic_theme.py
│   ├── install_theme.py
│   ├── install_demo_setup.py
│   ├── install_author_visualizer.py
│   ├── install_graphrag_queries.py
│   ├── install_dependency_queries.py
│   ├── install_fsm_queries.py
│   ├── patch_visualizer.py
│   ├── enhance_knowledge_transfer.py
│   ├── create_snapshot_of_edges.py
│   ├── create_oneshard_database.py
│   └── migrate_to_oneshard.sh
└── archive/               Historical debug/migration scripts (reference only)
```

---

## Pipeline and orchestration

### `rebuild_database.sh`

Master shell pipeline that runs the full database rebuild end-to-end. It ties together multi-repo ingestion, graph definition, inference/bridging, SNAPSHOT_OF edges, and visualizer assets.

**Phases (8 steps)**:

| Phase | Step | What runs |
|-------|------|-----------|
| 1 | Data ingestion | `multi_repo/ingest_repo.py --no-clone` — temporal ETL, deep RTL, GraphRAG (repos must exist under `repos/` or configured paths; run `ingest_repo.py` without `--no-clone` first if you need clones) |
| 2 | Named graph | `temporal/create_temporal_graph.py` — `IC_Temporal_Knowledge_Graph` |
| 3 | Situations | `src/situation_detector.py --all` |
| 4 | Semantic bridges | `src/rtl_semantic_bridge.py --all` (RESOLVED_TO) |
| 5 | Cross-repo bridges | `src/cross_repo_bridge.py --all` |
| 6 | SNAPSHOT_OF | `setup/create_snapshot_of_edges.py` (temporal → HEAD modules) |
| 7 | Theme | `setup/install_ic_theme.py` — Integrated Circuit theme |
| 8 | Demo UI | `setup/install_demo_setup.py` — saved queries + canvas actions |

**Usage**:

```bash
./scripts/rebuild_database.sh                      # full rebuild
./scripts/rebuild_database.sh --skip-ingestion   # data already loaded
./scripts/rebuild_database.sh --skip-visualizer  # skip theme + demo setup
```

**Prerequisites**: `.env` with `ARANGO_*` variables; Python deps; repos cloneable or already present per `repo_registry.yaml`.

---

### `master_etl.py`

Legacy **single-repository** ETL orchestrator: runs `src/` extractors (RTL, Git, FSM, etc.), loads JSON via `load_data.py`, authors ETL, consolidation/bridging. Use when working against the classic one-repo flow rather than `multi_repo/ingest_repo.py`.

**Usage**:

```bash
python3 scripts/master_etl.py
```

---

### `multi_repo/run_all_repos.sh`

Batch wrapper around `ingest_repo.py`: loads `.env`, prefers project `.venv`, and forwards flags (`--repo`, `--no-clone`, `--no-temporal`, `--no-graphrag`, `--dry-run`, `--commit-limit`, `--embedding-backend`, etc.).

**Usage**:

```bash
./scripts/multi_repo/run_all_repos.sh
./scripts/multi_repo/run_all_repos.sh --repo mor1kx
./scripts/multi_repo/run_all_repos.sh --no-graphrag --dry-run
```

---

### `multi_repo/ingest_repo.py`

Config-driven **multi-repo** ingestion: clone/update repos from `repo_registry.yaml`, run temporal ETL, deep RTL extraction, local GraphRAG, and load into ArangoDB.

**Usage**:

```bash
PYTHONPATH=src python3 scripts/multi_repo/ingest_repo.py
PYTHONPATH=src python3 scripts/multi_repo/ingest_repo.py --repo ibex
PYTHONPATH=src python3 scripts/multi_repo/ingest_repo.py --repo mor1kx --no-clone --dry-run
```

---

### `multi_repo/clone_manager.py`

Git helper used by the ingest pipeline: clones on first run, `git pull` on later runs; honors `local_path` overrides (e.g. `or1200` submodule). Import `ensure_clone` from other tools if needed.

---

### `temporal/run_temporal_etl.sh`

Runs the **single-repo** temporal path: `etl_temporal_git.py` (commit replay into JSONL) then `load_temporal_data.py`. Defaults to the `or1200` submodule path; supports `--limit`, `--dry-run`, `--repo`, `--branch`.

**Usage**:

```bash
./scripts/temporal/run_temporal_etl.sh
./scripts/temporal/run_temporal_etl.sh --limit 10 --dry-run
```

---

### `temporal/create_temporal_graph.py`

Creates or recreates the **`IC_Temporal_Knowledge_Graph`** named graph: scans existing collections and builds edge definitions (temporal RTL, GraphRAG collections per repo prefix, cross-repo edges, etc.). Deletes and recreates the graph document only; **does not** delete vertex/edge data.

**Usage**:

```bash
PYTHONPATH=src python3 scripts/temporal/create_temporal_graph.py
```

---

### `temporal/load_temporal_data.py`

Loads temporally annotated RTL nodes/edges from JSONL (from `etl_temporal_git.py`) into ArangoDB; ensures collections and temporal indexes.

**Usage**:

```bash
PYTHONPATH=src python3 scripts/temporal/load_temporal_data.py
PYTHONPATH=src python3 scripts/temporal/load_temporal_data.py --dry-run
```

---

## Diagnostics and smoke tests

### `smoke_test.py`

Lightweight connectivity check: no GraphRAG calls, no import. Verifies ArangoDB config and optionally that the configured named graph and collections exist.

**Usage**:

```bash
python3 scripts/smoke_test.py
python3 scripts/smoke_test.py --require-graph
python3 scripts/smoke_test.py --check-graphrag   # also verify GraphRAG collection names exist
```

---

### `diagnose_graphrag.py`

GraphRAG import diagnostic: configuration summary, collection counts, and importer/service checks. Requires an importer service ID as the first argument.

**Usage**:

```bash
python3 scripts/diagnose_graphrag.py <importer_service_id>
```

---

### `validate_er_migration.py`

Validates that the **arango-entity-resolution** package imports and basic similarity APIs work after an ER library upgrade or migration.

**Usage**:

```bash
python3 scripts/validate_er_migration.py
```

---

### `list_bridging_examples.py`

Lists strong **RESOLVED_TO** bridging examples (RTL modules, ports, signals → golden entities) for demos. Optional `--json` for machine-readable output.

**Usage**:

```bash
python3 scripts/list_bridging_examples.py
python3 scripts/list_bridging_examples.py --json
```

---

## Customer and local tooling

### `customer_workflow.py`

Driver for **numbered exercise databases**: sets `ARANGO_DATABASE` for subprocesses so customers can run ETL, bridging, and visualizer setup against `ic-knowledge-graph-N` without hand-editing `.env`. Can create a OneShard DB via API when missing.

See script `--help` for flags and workflow steps.

---

### `local_er_mcp.sh`

Launches the **local** ArangoDB Entity Resolution MCP server against Docker ArangoDB (`localhost:8530`), with env vars set for this project. Paths/venv inside the script are **machine-specific**; adjust for your install. Used with Cursor `mcp.json` entry for local ER MCP.

---

## Database layout and migration

### `setup/create_oneshard_database.py`

Creates an ArangoDB database with **OneShard** (`sharding=single`) using project `.env` credentials. Optional Enterprise replication env vars.

**Usage**:

```bash
PYTHONPATH=src python3 scripts/setup/create_oneshard_database.py
PYTHONPATH=src python3 scripts/setup/create_oneshard_database.py --name ic-knowledge-graph-temporal
```

---

### `setup/migrate_to_oneshard.sh`

Migrates an existing database to OneShard layout: **dump → drop → create empty OneShard DB → restore**. Uses host `arangodump`/`arangorestore` when available, otherwise Docker (`ARANGO_CLI_IMAGE`, default `arangodb:3.12`). Requires `.env` with endpoint, credentials, and `ARANGO_DATABASE`.

---

### `migrate_collections.py`

Copies a fixed list of collections (OR1200 GraphRAG collections + visualizer system collections) from a **source** database to a **target** database. Set `ARANGO_SOURCE_DB` / `ARANGO_TARGET_DB` (or `SOURCE_DB` / `TARGET_DB`).

---

## Setup: Graph Visualizer and themes

Open the graph once in the Web UI so `_graphThemeStore`, `_canvasActions`, `_viewpoints`, and `_viewpointActions` exist before running installers.

### `setup/install_ic_theme.py`

Installs the **Integrated Circuit** theme and IC-specific canvas actions for **`IC_Temporal_Knowledge_Graph`**, reading `docs/hardware_design_theme.json`.

**Usage**:

```bash
PYTHONPATH=src python3 scripts/setup/install_ic_theme.py
```

---

### `setup/install_theme.py`

Installs the **hardware-design** theme document into `_graphThemeStore` from `docs/hardware_design_theme.json` (colors, icons, labels). Prefer `install_ic_theme.py` for the full temporal demo graph experience.

**Usage**:

```bash
python3 scripts/setup/install_theme.py
```

---

### `setup/install_demo_setup.py`

Installs demonstration **saved queries** and **canvas actions** from packaged JSON (`DEMO_SETUP_QUERIES.json`); wires `_viewpointActions`. Does **not** install the theme — run `install_ic_theme.py` (or `install_theme.py`) separately.

**Usage**:

```bash
python3 scripts/setup/install_demo_setup.py
python3 scripts/setup/install_demo_setup.py --db ic-knowledge-graph-temporal
python3 scripts/setup/install_demo_setup.py --graph IC_Temporal_Knowledge_Graph
```

---

### `setup/install_author_visualizer.py`

Installs saved queries and canvas actions for **Author** expertise / knowledge-transfer exploration; links to the **`IC_Temporal_Knowledge_Graph`** viewpoint.

**Usage**:

```bash
python3 scripts/setup/install_author_visualizer.py
```

**Queries installed** (10): Top Maintainers, Find Experts, Bus Factor, Collaboration Network, Knowledge Impact, Expertise Areas, Knowledge Gaps, Succession Planning, Team Coverage Matrix, Commit History Timeline.

**Canvas actions** (6): Author expertise, commits, module maintainers, collaborators, specification impact, commit context.

---

### `setup/install_graphrag_queries.py`

Installs GraphRAG-oriented **saved queries** and **canvas actions** (RTL portrait, golden entity view, RESOLVED_TO bridge, cross-repo lineage), scoped to `TEMPORAL_GRAPH_NAME` / `IC_Temporal_Knowledge_Graph`.

**Usage**:

```bash
PYTHONPATH=src python3 scripts/setup/install_graphrag_queries.py
```

---

### `setup/install_dependency_queries.py`

Installs **module dependency** saved queries and canvas actions (legacy graph names may appear in embedded AQL — align with your named graph if needed).

---

### `setup/install_fsm_queries.py`

Installs **FSM** analysis saved queries and canvas actions for state-machine exploration in the visualizer.

---

### `setup/patch_visualizer.py`

One-shot **visualizer repair**: extends Default theme for RTL collections, adds missing vertex collections to the named graph, reinstalls theme from `docs/hardware_design_theme.json`. Run after schema or theme changes if the UI misses nodes or themes.

**Usage**:

```bash
PYTHONPATH=src python3 scripts/setup/patch_visualizer.py
```

---

### `setup/create_snapshot_of_edges.py`

Builds **SNAPSHOT_OF** edges from temporal RTL module snapshots to **HEAD** deep-RTL modules (same logical module, full ports/signals/etc.). Idempotent (truncates and rebuilds). Adds the edge collection to **`IC_Temporal_Knowledge_Graph`** when missing.

**Usage**:

```bash
PYTHONPATH=src python3 scripts/setup/create_snapshot_of_edges.py
```

---

### `setup/enhance_knowledge_transfer.py`

Generates knowledge-transfer **risk assessments** and per-module **plans**; writes Markdown under `docs/knowledge-transfer/`.

**Usage**:

```bash
python3 scripts/setup/enhance_knowledge_transfer.py
```

**Outputs**: `KNOWLEDGE_TRANSFER_RISK_REPORT.md`, `docs/knowledge-transfer/plans/*.md`.

---

## Archived scripts

Historical debugging and one-off migrations. Not required for normal operation.

### `scripts/archive/` — debug and visualizer fixes

- `check_queries.py` — Verify saved query installation
- `check_viewpoints.py` — Viewpoint document checks
- `compare_actions.py` — Compare canvas actions
- `diagnose_actions.py` — Canvas action diagnostics
- `fix_action_names.py` — Add `name` field to actions
- `fix_canvas_actions.py` — Fix action linking
- `reinstall_actions.py` — Reinstall canvas actions

### `scripts/archive/` — migration

- `migrate_to_enrichments.sh` — Legacy migration to ER enrichments (completed)

---

## Development workflow

### Full temporal stack (recommended for multi-repo demo)

```bash
cp env.template .env   # configure ARANGO_* and paths
pip install -r requirements.txt
./scripts/rebuild_database.sh
```

Optional: knowledge-transfer reports:

```bash
python3 scripts/setup/enhance_knowledge_transfer.py
```

### Legacy single-repo workflow

For older single-repo flows:

```bash
./src/import_all.sh
python3 src/create_graph.py
python3 src/bridger.py
python3 src/etl_authors.py
python3 scripts/setup/install_theme.py
python3 scripts/setup/install_author_visualizer.py
python3 scripts/setup/install_demo_setup.py
python3 scripts/setup/enhance_knowledge_transfer.py
```

### Regular maintenance (legacy)

```bash
python3 src/etl_authors.py
python3 scripts/setup/enhance_knowledge_transfer.py
```

---

## Script dependencies

Most scripts expect:

- **`src/db_utils.py`**, **`src/config.py`** / **`src/config_temporal.py`** — DB and graph names
- **`.env`** — Copy from `env.template`; set `ARANGO_MODE`, endpoints, database name, credentials
- **ArangoDB** — Reachable from your machine

**Import pattern**:

```python
import sys
sys.path.insert(0, "src")
from db_utils import get_db
```

---

## Adding new scripts

1. **Production / pipeline** — Place under `scripts/`, `scripts/setup/`, `scripts/multi_repo/`, or `scripts/temporal/` by role; document in this README.
2. **One-off debug** — Move to `scripts/archive/` when done.
3. **Graph Visualizer assets** — Follow the same patterns as existing installers (`_graphThemeStore`, `_editor_saved_queries`, `_canvasActions`); see `docs/` and the ArangoDB Graph Visualizer docs for collection shapes.

---

## See also

- [Main README](../README.md) — Project overview
- [ETL Documentation](../docs/project/) — Data pipeline details
- [Knowledge Transfer Guide](../docs/knowledge-transfer/) — Expertise mapping
- [Demo Setup](../docs/DEMO_README.md) — Presentation preparation

---

**Last Updated**: March 2026
