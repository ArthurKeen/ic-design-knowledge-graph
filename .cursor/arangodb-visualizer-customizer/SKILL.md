---
name: arangodb-visualizer-customizer
description: Installs and maintains ArangoDB Graph Visualizer customization assets (themes, saved queries, canvas actions, and viewpoint links). Use when the user mentions ArangoDB visualizer, Graph Visualizer, themes, canvas actions, saved queries, stored queries, or collections like _graphThemeStore, _canvasActions, _editor_saved_queries, _viewpoints, or _viewpointActions.
---

# ArangoDB Visualizer Customizer (themes, saved queries, canvas actions)

This skill provides a repeatable, idempotent workflow for customizing the ArangoDB **Graph Visualizer** by installing:

- **Themes** (colors/icons) in `_graphThemeStore`
- **Saved queries** in `_editor_saved_queries`
- **Canvas actions** in `_canvasActions`
- **Viewpoint links** (so actions show up in the UI) in `_viewpointActions` edges from `_viewpoints/*` → `_canvasActions/*`

## Quick start checklist (most reliable order)

1. **Confirm graph + DB**: target database name and graph name (e.g. `IC_Knowledge_Graph`).
2. **Ensure a viewpoint exists**:
   - Open the graph once in the web UI (Graphs → your graph). This typically creates `_viewpoints` docs.
3. **Install theme** (target DB):
   - Upsert into `_graphThemeStore` (by `graphId` + `name`).
4. **Install saved queries** (often `_system`, sometimes target DB):
   - Upsert into `_editor_saved_queries`.
5. **Install canvas actions** (often `_system`, sometimes target DB):
   - Upsert into `_canvasActions`.
   - Ensure each action has `name` (UI expects it) and a stable `_key`.
6. **Link actions to the viewpoint** (target DB):
   - Insert edges in `_viewpointActions` from the correct `_viewpoints/_id` to `_canvasActions/<_key>`.
7. **Verify**:
   - Counts look sane; actions appear in UI right-click menu; queries appear in Queries panel; theme selectable in Legend.

## Key implementation details (what the agent must know)

### Where these “special collections” live

ArangoDB UI metadata may be stored either:

- **In the target database**, or
- **In `_system`** (common for `_editor_saved_queries` / `_canvasActions`)

Best practice:

- Treat **themes** as **target-DB** assets (install into the same DB as the graph).
- Treat **saved queries** and **canvas actions** as **system-level** assets by default (install into `_system`) *but* fall back to target DB if `_system` is locked down or the environment clearly uses target DB for those collections.

Concrete example patterns (from `ic-knowledge-graph`):
- Theme: `scripts/setup/install_theme.py` installs into target DB `_graphThemeStore`.
- Saved queries + actions: several installers use `_system` (`get_system_db()`), while `scripts/setup/install_demo_setup.py` uses target DB.

### Viewpoints and linking canvas actions

Canvas actions do **not** show up in Graph Visualizer until they are linked to a graph “viewpoint”.

- Viewpoints live in: `_viewpoints` (target DB)
- Links live in: `_viewpointActions` (edge collection, target DB)
- Edge shape:
  - `_from`: the viewpoint `_id` (e.g. `_viewpoints/12345`)
  - `_to`: the action `_id` (commonly `_canvasActions/<action_key>`)

If `_viewpoints` is empty:
- The user likely hasn’t opened the graph in the Visualizer yet.
- Tell them to open it once, then rerun the installer.

### Minimal document shapes (use these defaults)

**Theme document** (`_graphThemeStore`):
- Must include `name`, `graphId`, `nodeConfigMap`, `edgeConfigMap`
- Add/refresh timestamps: `createdAt`, `updatedAt`
- Upsert key: `graphId + name`

**Saved query** (`_editor_saved_queries`):
- Use `title`/`name` and `queryText` (AQL)
- Optionally include: `description`, `bindVariables`
- If the UI expects database scoping, add a `databaseName` field set to the target DB
- Upsert key: stable `_key` when possible; otherwise match on `title`/`name`

**Canvas action** (`_canvasActions`):
- Use stable `_key` (snake_case), plus `name`, `title`, `queryText`, `graphId`, `bindVariables`
- If `title` exists but `name` doesn’t, set `name = title` (UI requires `name` in practice)
- Upsert key: `_key` (preferred) or match on `name`
- **`bindVariables` for node-based actions**: Use `{"nodes": []}`. The node selector provides an array of selected vertices/edges; the query receives them as `@nodes`. Use `FOR node IN @nodes` directly. Do not add `IS_ARRAY` normalization or empty-result fallbacks—the Visualizer expects the query to return paths/edges in the standard format.

### Idempotency rules (must follow)

When installing:
- **Never create duplicates**.
- Prefer **upsert/update**:
  - If a doc exists → update content and set `updatedAt`
  - If missing → insert with stable `_key` and set `createdAt`/`updatedAt`
- For viewpoint links:
  - Insert only if an edge with same `_from` and `_to` does not already exist.

## Recommended workflow to implement in a project

### 1) Create “installer” scripts in the repo

Include scripts that can be run repeatedly:
- `scripts/setup/install_theme.py`
- `scripts/setup/install_*_queries.py` (saved queries)
- `scripts/setup/install_*_actions.py` (canvas actions)
- Or one “demo setup” script that installs queries + actions + links (like `scripts/setup/install_demo_setup.py`)

Prefer Python + `python-arango`.

### 2) Store assets in version control

Keep assets as JSON files under `docs/`:
- `docs/<your_theme>.json`
- `docs/<your_saved_queries>.json` or `docs/DEMO_SETUP_QUERIES.json`

This makes the DB customization reproducible and reviewable.

### 3) Verify in UI (manual steps)

- Graph Visualizer:
  - **Theme**: Graphs → graph → Legend → theme dropdown
  - **Saved queries**: Queries panel / query dropdown
  - **Canvas actions**: right-click node/canvas → Canvas Actions

### Ontology vs data graphs

For **ontology graphs** (metadata only: classes, properties, domain/range):
- Restrict theme `nodeConfigMap` and `edgeConfigMap` to ontology collections (Class, Property, Ontology, ObjectProperty, DatatypeProperty, OntologyGraph_UnknownResource; domain, range, subClassOf, type).
- Restrict canvas actions to ontology vertex types only. Do not create expand actions for data collections (Person, Organization, etc.)—they don't belong in an ontology view.
- For DatatypeProperty/ObjectProperty expand actions: filter on the *traversed* vertex `v`, not the start `node` (e.g. `FILTER IS_SAME_COLLECTION("DatatypeProperty", v)`), and use ontology edges only (domain, range, subClassOf—omit type if not needed).

### Cluster deployments

- Include a `WITH` clause listing all vertex and edge collections that may be encountered in the traversal (required for cluster mode).

## Troubleshooting (common failures)

### Actions don’t appear
- `_viewpoints` empty → open graph in UI once.
- Wrong viewpoint selected → choose viewpoint whose `graphId` matches the actions’ `graphId`.
- Missing `_viewpointActions` edge collection or edges not created.

### Queries appear but run against wrong DB
- Ensure query doc includes `databaseName` (if used in your environment).
- Ensure `bindVariables` include correct vertex IDs (e.g. `RTL_Module/or1200_cpu`) for the target DB.

### Theme not selectable
- `_graphThemeStore` missing in target DB → open graph in UI once (some setups initialize system collections lazily).
- Theme `graphId` does not match actual graph name in DB.

## Concrete reference (existing working examples)

Use these as “known-good” templates:
- `fraud-intelligence/scripts/install_graph_themes.py` — themes + canvas actions; ontology-only handling for OntologyGraph
- `fraud-intelligence/docs/themes/ontology_theme.json` — ontology theme (Class, Property, ObjectProperty, DatatypeProperty, OntologyGraph_UnknownResource)
- `ic-knowledge-graph/scripts/setup/install_theme.py`
- `ic-knowledge-graph/scripts/setup/install_demo_setup.py`
- `ic-knowledge-graph/scripts/setup/install_dependency_queries.py`
- `ic-knowledge-graph/scripts/setup/install_fsm_queries.py`
- `ic-knowledge-graph/scripts/setup/install_author_visualizer.py`

