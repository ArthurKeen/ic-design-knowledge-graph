# Cadence Tuesday Demo - Preparation Guide

## Overview

This directory contains everything you need for the Tuesday Cadence demonstration of the Integrated Circuit (IC) Design Knowledge Graph. The demo showcases how ArangoDB's Graph Visualizer enables exploration of integrated circuit designs through semantic bridges between RTL code, specifications, and Git history.

## Customer quickstart (numbered database exercise)

Customers can explore the preloaded demo database `ic-knowledge-graph-temporal` in read-only mode, then create a numbered sandbox database `ic-knowledge-graph-1`, `ic-knowledge-graph-2`, … to run the full workflow (GraphRAG UI document import + ETL + consolidation + bridging + Visualizer setup).

Follow the step-by-step guide in [`docs/CUSTOMER_EXERCISE_WORKFLOW.md`](CUSTOMER_EXERCISE_WORKFLOW.md).

## Demo Materials

### 1. DEMO_SCRIPT.md
**Purpose**: Complete demonstration guide and reference 
**Contents**:
- 30-45 minute structured demo flow in 6 parts
- 12 saved queries with explanations and narration
- 10 canvas actions for interactive exploration
- Expected questions with detailed technical responses
- Quick reference cards and keyboard shortcuts
- Agent integration code examples

**For the current multi-repo temporal demo, see [TEMPORAL_DEMO_SCRIPT.md](TEMPORAL_DEMO_SCRIPT.md) as your primary reference during the meeting.**

### 2. DEMO_SETUP_QUERIES.json
**Purpose**: Pre-configured queries, actions, and theme 
**Contents**:
- 12 saved queries in ArangoDB format
- 10 canvas action definitions
- Custom visualization theme with optimized colors and icons

**This file is imported automatically by the installer script.**

### 3. install_demo_setup.py
**Purpose**: Automated installation of demo components 
**What it does**:
- Installs saved queries into `_editor_saved_queries`
- Installs canvas actions into `_canvasActions`
- Creates `_viewpointActions` edges linking actions to the graph
- Installs the visualization theme
- Verifies installation completeness

---

## Pre-Demo Setup (30 minutes before meeting)

### Step 1: Verify Database Status

```bash
# Ensure ArangoDB is running and accessible
# Check that the IC_Temporal_Knowledge_Graph exists
cd /Users/arthurkeen/code/ic-knowledge-graph
python -c "from src.db_utils import get_db; db = get_db(); print('Database:', db.name); print('Graph exists:', db.has_graph('IC_Temporal_Knowledge_Graph'))"
```

**Expected output**:
```
Database: ic-knowledge-graph-temporal
Graph exists: True
```

If the graph doesn't exist, run the full rebuild:
```bash
bash scripts/rebuild_database.sh
```

### Step 2: Install Visualization Theme

```bash
python scripts/setup/install_ic_theme.py
```

This installs the `hardware-design` theme into `_graphThemeStore`. The theme
configures node colors, icons, and edge styling for all processor collections.

### Step 3: Install Demo Queries and Actions

```bash
python scripts/setup/install_demo_setup.py
```

This installs saved queries, canvas actions, and viewpoint links. It does
**not** install the visualization theme — that is handled separately by
`install_ic_theme.py` (Step 2).

### Step 4: Configure Visualizer

1. Open ArangoDB web interface in your browser
2. Select database: `ic-knowledge-graph-temporal`
3. Navigate to: **Graphs** → **IC_Temporal_Knowledge_Graph**
4. The Graph Visualizer opens

**Apply the theme**:
- Click **Legend** button (top right)
- Click the theme dropdown (top of Legend panel)
- Select **"hardware-design"**
- The canvas will automatically update with the new colors and icons

**Verify color scheme**:
- RTL_Module: Green with microchip icon
- RTL_Port: Pink with USB port icon
- RTL_Signal: Green with signal icon
- RTL_LogicChunk: Purple with code braces icon
- OR1200_Golden_Entities: Gold with alien icon
- GitCommit: Purple with commit icon
- RESOLVED_TO edges: Gold, thick (highlighted semantic bridges)
- WIRED_TO edges: Pink, thick

### Step 5: Test Key Queries

Run these quick tests to ensure everything works:

**Test 1: Graph Overview**
- Click **Queries** (top-left widget)
- Select "Graph Overview - Sample From All Collections"
- Click **Run**
- **Expected**: Mixed canvas with blue, green, and red nodes

**Test 2: Canvas Action**
- Clear canvas (bottom-right)
- Click **Search & add nodes to canvas**
- Search for "alu" in RTL_Module
- Add the `or1200_alu` node
- Right-click the node → **Canvas Action** → **Show Entity Resolutions**
- **Expected**: Green entity nodes appear connected by gold edges

**Test 3: Semantic Bridge Quality**
- Click **Queries**
- Select "Top Scoring Semantic Links"
- Click **Run**
- **Expected**: Nodes connected by gold RESOLVED_TO edges
- Double-click an edge to inspect the `score` attribute

If all tests pass, you're ready for the demo!

---

## Demo Day Checklist

### 15 Minutes Before
- [ ] Open ArangoDB web interface
- [ ] Load IC_Temporal_Knowledge_Graph in visualizer
- [ ] Verify "hardware-design" theme is active
- [ ] Clear canvas (start fresh)
- [ ] Have DEMO_SCRIPT.md open for reference
- [ ] Test network connectivity (if remote database)
- [ ] Close unnecessary browser tabs/applications

### Opening Remarks Prep
- [ ] Review the "Overview & Context" section in the demo script
- [ ] Have the schema diagram ready: `docs/project/SCHEMA.md`
- [ ] Know the key stats:
 - 4 processors (OR1200, IBEX, MOR1KX, Marocchino), ~6,400 modules
 - ~3,800 commits across repos, 381 temporal epochs, 721 design situations
 - 193 RESOLVED_TO bridges, 61 CROSS_REPO_SIMILAR_TO edges

### Demo Flow Bookmarks
Have these queries ready to access quickly:
1. **Part A**: Graph Overview - Sample From All Collections
2. **Part B**: Manual search for "alu" + "Show Entity Resolutions" action
3. **Part C**: CPU Module Hierarchy
4. **Part D**: Find Entity by Name (bind: "exception")
5. **Part E**: Recent Commits and Modified Modules
6. **Part F**: Shortest Path (built-in, no query)

### Backup Plan
If live demo fails (network, database, etc.):
- Use the schema diagram to explain the architecture
- Walk through the AQL queries in the script as pseudocode
- Show the agent integration code examples (Appendix B)
- Refer to the WALKTHROUGH.md for data statistics

---

## Common Issues & Troubleshooting

### Issue: "Graph IC_Temporal_Knowledge_Graph not found"
**Solution**: Run the graph creation script:
```bash
python src/create_temporal_graph.py
```

### Issue: "No data returned from queries"
**Solution**: Collections may be empty. Re-run the full rebuild:
```bash
bash scripts/rebuild_database.sh
```

### Issue: "Canvas actions not appearing in context menu"
**Solution**: Check that `_viewpointActions` edges were created:
```bash
python -c "from src.db_utils import get_db; db = get_db(); print('Actions edges:', db.collection('_viewpointActions').count())"
```
If count is 0, re-run the installer: `python scripts/setup/install_demo_setup.py`

### Issue: "Theme not applying colors"
**Solution**: 
1. Verify theme was installed: `python -c "from src.db_utils import get_db; db = get_db(); print('hardware-design theme:', len(list(db.collection('_graphThemeStore').find({'name': 'hardware-design'}))))"`
2. If count is 0, run: `python scripts/setup/install_ic_theme.py`
3. In visualizer, manually select "hardware-design" from theme dropdown
4. If still broken, refresh the browser page

### Issue: "Query returns paths but visualizer shows nothing"
**Solution**: 
- Queries must return paths (`p`), vertices/edges arrays, or documents
- Check that the query uses `RETURN p` not `RETURN {data: p}`
- Try clearing canvas and re-running

---

## Post-Demo Actions

### If the demo goes well:
1. Share database credentials with stakeholders for hands-on exploration
2. Schedule technical deep-dive meeting
3. Prepare scaling analysis (SmartGraphs, cluster sizing)
4. Discuss integration with their existing Neo4j/FAISS setup

### Follow-up materials to provide:
- [ ] Copy of DEMO_SCRIPT.md
- [ ] Access to demo instance (read-only)
- [ ] ETL pipeline source code
- [ ] Agent integration examples
- [ ] Performance benchmarking results
- [ ] Migration guide (Neo4j → ArangoDB)

### Document feedback:
- Record questions asked (for improving Q&A section)
- Note which parts resonated most
- Capture feature requests or concerns
- Document any technical objections

---

## Quick Command Reference

```bash
# Install theme
python scripts/setup/install_ic_theme.py

# Install queries and actions
python scripts/setup/install_demo_setup.py

# Verify setup
python -c "from src.db_utils import get_db; db = get_db(); print('Theme installed:', len(list(db.collection('_graphThemeStore').find({'name': 'hardware-design'}))) > 0)"

# Full rebuild (all processors, temporal graph, bridges)
bash scripts/rebuild_database.sh

# Check database status
python -c "from src.db_utils import get_db; db = get_db(); print('Collections:', len(db.collections())); print('Graph:', db.has_graph('IC_Temporal_Knowledge_Graph'))"

# Count semantic bridges
python -c "from src.db_utils import get_db; db = get_db(); print('RESOLVED_TO edges:', db.collection('RESOLVED_TO').count())"
```

---

## Key Talking Points

1. **Hierarchical Semantic Bridge**: "Trace from high-level specs down to specific Verilog code lines"
2. **Type-Safe Resolution**: "Prevents nonsensical matches like 'clock signal' → 'instruction set'"
3. **Temporal Audit**: "Time-travel through design evolution using Git commits"
4. **Token Savings**: "10x reduction in LLM context size by using graph traversal"
5. **Scalability**: "Ready for billions of edges with SmartGraphs sharding"

---

## Contact & Support

- **Demo Script**: `/path/to/project/docs/DEMO_SCRIPT.md`
- **Schema Reference**: `/path/to/project/docs/project/SCHEMA.md`
- **Walkthrough Stats**: `/path/to/project/docs/project/WALKTHROUGH.md`
- **AQL Reference**: `/path/to/project/docs/reference/aql_ref.md`

**Good luck with the demo!** 
