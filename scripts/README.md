# Scripts Directory

Utility scripts for setup, maintenance, and debugging of the Integrated Circuit (IC) Design Knowledge Graph demo.

---

## Directory Structure

```
scripts/
├── setup/           - Installation and setup scripts
├── archive/         - Archived debugging/fix scripts
└── README.md       - This file
```

---

## Setup Scripts

Production-ready scripts for installing and configuring the system.

### `setup/install_author_visualizer.py`

Installs saved queries and canvas actions for Author expertise mapping.

**Usage**:
```bash
python3 scripts/setup/install_author_visualizer.py
```

**What it does**:
- Installs 10 saved queries for knowledge transfer analysis
- Installs 6 canvas actions for interactive exploration
- Links actions to the OR1200_Knowledge_Graph viewpoint

**Queries installed**:
1. Top Maintainers by Module Count
2. Find Experts for a Module
3. Bus Factor Analysis
4. Collaboration Network
5. Knowledge Impact (Author → Specs)
6. Expertise Areas by Module Type
7. Knowledge Gaps
8. Succession Planning
9. Team Coverage Matrix
10. Commit History Timeline

**Canvas actions installed**:
1. Show Author's Expertise
2. Show Author's Commits
3. Show Module Maintainers
4. Show Collaborators
5. Show Author's Specification Impact
6. Show Commit Context

### `setup/enhance_knowledge_transfer.py`

Generates knowledge transfer risk assessments and action plans.

**Usage**:
```bash
python3 scripts/setup/enhance_knowledge_transfer.py
```

**What it does**:
- Enriches top authors with team/role information
- Calculates knowledge transfer risk scores for all modules
- Generates detailed knowledge transfer plans for high-risk modules
- Creates executive risk report

**Output files**:
- `docs/knowledge-transfer/KNOWLEDGE_TRANSFER_RISK_REPORT.md`
- `docs/knowledge-transfer/plans/*.md` (individual transfer plans)

### `setup/install_demo_setup.py`

Installs demo queries and canvas actions for demonstrations.

**Usage**:
```bash
python3 scripts/setup/install_demo_setup.py
```

**What it does**:
- Installs saved queries from DEMO_SETUP_QUERIES.json
- Creates canvas actions for demo scenarios
- Links to viewpoint for OR1200_Knowledge_Graph

### `list_bridging_examples.py`

Lists strong bridging examples for demonstration (RTL_Module and subcomponents → Golden Entities).

**Usage**:
```bash
python3 scripts/list_bridging_examples.py
python3 scripts/list_bridging_examples.py --json   # machine-readable
```

**What it does**:
- Queries all RESOLVED_TO edges and enriches with source label and target entity name
- Groups by RTL_Module, RTL_Port, RTL_Signal
- Prints module-level bridges (if any), port bridges by parent module, signal bridges by parent module
- Suggests demo entry points (modules with most bridged ports/signals)

Use this after running `bridger_bulk.py` to find good nodes for a bridging demo (e.g. a module whose ports/signals resolve to doc entities).

### `setup/install_theme.py`

Installs the 'hardware-design' visualization theme.

**Usage**:
```bash
python3 scripts/setup/install_theme.py
```

**What it does**:
- Reads theme configuration from `docs/or1200_theme.json`
- Installs/updates theme in `_graphThemeStore` collection
- Configures colors, icons, and labels for all node/edge types

---

## Archived Scripts

Historical debugging and fix scripts. Kept for reference but not needed for normal operations.

### Debug Scripts (scripts/archive/)

These were used during development to diagnose and fix issues with the Graph Visualizer:

- `check_queries.py` - Verify saved queries installation
- `check_viewpoints.py` - Check viewpoint document structure
- `compare_actions.py` - Compare working vs installed canvas actions
- `diagnose_actions.py` - Diagnose canvas action issues
- `fix_action_names.py` - Add name field to canvas actions
- `fix_canvas_actions.py` - Fix canvas action linking
- `reinstall_actions.py` - Clean reinstall of canvas actions

### Migration Scripts (scripts/archive/)

- `migrate_to_enrichments.sh` - Migrate from local ic_enrichment to ER library (completed)

**Note**: These scripts are archived and typically don't need to be run again. They're kept for historical reference and troubleshooting.

---

## Development Workflow

### Initial Setup

After cloning the repository:

```bash
# 1. Set up environment
cp env.template .env
# Edit .env with your configuration

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run main ETL pipeline
./src/import_all.sh
python3 src/create_graph.py
python3 src/bridger.py
python3 src/etl_authors.py

# 4. Install visualizer features
python3 scripts/setup/install_theme.py
python3 scripts/setup/install_author_visualizer.py
python3 scripts/setup/install_demo_setup.py

# 5. Generate knowledge transfer reports
python3 scripts/setup/enhance_knowledge_transfer.py
```

### Regular Maintenance

```bash
# Update author relationships after new commits
python3 src/etl_authors.py

# Regenerate knowledge transfer risk reports
python3 scripts/setup/enhance_knowledge_transfer.py
```

---

## Script Dependencies

All scripts require:
- `src/db_utils.py` - Database connection utilities
- `.env` file - Configuration (copy from `env.template`)
- ArangoDB connection - Must be running and accessible

**Import pattern**:
```python
import sys
sys.path.append('src')
from db_utils import get_db
```

---

## Adding New Scripts

When adding new utility scripts:

1. **Production scripts** → `scripts/setup/`
   - Well-tested, production-ready
   - Clear documentation
   - Error handling

2. **Development/debug scripts** → Use temporarily, then move to `scripts/archive/`
   - Experimental features
   - One-off fixes
   - Diagnostic tools

3. **Update this README** with script purpose and usage

---

## See Also

- [Main README](../README.md) - Project overview
- [ETL Documentation](../docs/project/) - Data pipeline details
- [Knowledge Transfer Guide](../docs/knowledge-transfer/) - Expertise mapping features
- [Demo Setup](../docs/DEMO_README.md) - Presentation preparation

---

**Last Updated**: January 8, 2026

