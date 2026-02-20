# Customer Exercise Workflow (Numbered Databases)

This demo supports two modes:

1. **Read-only exploration** (no code): use the preloaded database `ic-knowledge-graph` in the ArangoDB Dashboard/Visualizer.
2. **Hands-on exercise** (recommended): create a numbered database `ic-knowledge-graph-1`, `ic-knowledge-graph-2`, …, import documents via the **GraphRAG UI**, then run a **single script** to perform ETL, consolidation, bridging, and Visualizer setup.

---

## Part A — Read-only exploration (preloaded demo DB)

1. Open the ArangoDB web UI.
2. Select database **`ic-knowledge-graph`**.
3. Navigate to **Graphs → `IC_Knowledge_Graph`**.
4. In Graph Visualizer:
   - Apply the **`hardware-design`** theme (Legend → theme dropdown).
   - Run saved queries and canvas actions provided in the demo setup.

This mode is safe for customers who want to learn the UI with no writes.

---

## Part B — Hands-on exercise (create a numbered database)

### Step 1 (Primary) — Create the database in the UI

1. ArangoDB UI → **Databases** → **Create database**
2. Name it: `ic-knowledge-graph-1` (or the next available number)
3. Ensure your user has permission to create collections/graphs in this database.

### Step 1 (Alternate) — Create the database via script/API

From the repo root:

```bash
python scripts/customer_workflow.py init-db --db ic-knowledge-graph-1
```

---

## Step 2 — Load the core knowledge graph (RTL + Git + semantic layer)

From the repo root:

```bash
python scripts/customer_workflow.py setup --db ic-knowledge-graph-1 --skip-graphrag
```

This will:
- run core ETL (RTL + Git + authors)
- create the graph (`IC_Knowledge_Graph`)
- install Visualizer assets (theme + saved queries + canvas actions)
- run a smoke verification

> Note: `--skip-graphrag` is recommended before the document import step, so the script does not try to consolidate/bridge GraphRAG entities that don’t exist yet.

---

## Step 3 — Import documents into the numbered DB (Official: GraphRAG UI)

### 3.1 Create/choose a GraphRAG project for the numbered DB

In the ArangoDB GraphRAG UI:
- Create a GraphRAG project associated with database `ic-knowledge-graph-1`
- Recommended naming convention:
  - Project name: `OR1200-1`
  - Collection prefix: `OR1200_`

### 3.2 Import OR1200 documents

Import the OR1200 PDF documents into the GraphRAG project using the UI.

After import, the database should contain (at minimum) these collections:
- `OR1200_Documents`
- `OR1200_Chunks`
- `OR1200_Entities`
- `OR1200_Relations`

---

## Step 4 — Post-import: consolidate + bridge documentation into RTL

After the GraphRAG UI import completes:

```bash
python scripts/customer_workflow.py setup --db ic-knowledge-graph-1
```

This will run:
- consolidation (`OR1200_Entities` → `OR1200_Golden_Entities`)
- bridging (`RESOLVED_TO` edges from RTL nodes to Golden Entities)
- reinstall/refresh Visualizer setup for the numbered DB
- run verification checks

---

## Step 5 — Verify in the Visualizer

1. ArangoDB UI → select database `ic-knowledge-graph-1`
2. Graphs → open `IC_Knowledge_Graph` **at least once**
   - This creates a `_viewpoints` document required for canvas actions.
3. Apply theme:
   - Legend → theme dropdown → `hardware-design`
4. Run a saved query (Queries panel) and a canvas action:
   - Search for a module like `or1200_alu` (collection `RTL_Module`)
   - Right-click → Canvas actions → “Show Entity Resolutions”

If canvas actions do not appear:
- open the graph once in Visualizer (creates `_viewpoints`)
- rerun:

```bash
python scripts/customer_workflow.py install-visualizer --db ic-knowledge-graph-1
```

---

## Optional: Notebook-based import

If you prefer notebooks over the GraphRAG UI, use:
- `docs/notebook/import_docs_to_numbered_db.ipynb`

The official/supported import method remains the **GraphRAG UI**.

