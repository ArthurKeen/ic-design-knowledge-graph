# IC Temporal Knowledge Graph Documentation

Welcome to the IC Temporal Knowledge Graph demo documentation. This project builds a multi-repo temporal knowledge graph spanning four open-source RISC processors (OR1200, IBEX, MOR1KX, Marocchino). This directory contains all project documentation organized by topic.

---

## Quick Navigation

### 📘 Getting Started
- **[Project Overview](../README.md)** - Main project README
- **[Temporal Demo Script](TEMPORAL_DEMO_SCRIPT.md)** - Primary walkthrough for the temporal knowledge graph
- **[Technical Presentation](TECHNICAL_PRESENTATION.md)** - Comprehensive technical presentation
- **[Walkthrough](project/WALKTHROUGH.md)** - Project walkthrough and examples
- **[Schema](project/SCHEMA.md)** - Database schema and structure
- **[PRD](project/PRD.md)** - Product Requirements Document

### 🚀 Improvements & Quality
- **[Bridging Technical Details](project/BRIDGING_TECHNICAL_DETAILS.md)** - Legacy OR1200 bridging/consolidation implementation details
- **[Customer Exercise Workflow](CUSTOMER_EXERCISE_WORKFLOW.md)** - Numbered sandbox database workflow

### 📚 Reference
- **[AQL Reference](reference/aql_ref.md)** - AQL query examples
- **[Optimization Guide](reference/optimization.md)** - Query optimization and VCI
- **[Integration Guide](reference/arangographrag-integration.md)** - ArangoGraphRAG integration
- **[GraphRAG Orchestration](reference/graphrag-orchestration.md)** - GraphRAG service orchestration guide

---

## Document Organization

```
docs/
├── README.md (this file)
├── TEMPORAL_DEMO_SCRIPT.md
├── CUSTOMER_EXERCISE_WORKFLOW.md
├── project/ # Core project documentation
└── reference/ # Reference materials
```

---

## Project Status

**Current Phase:** Production — Multi-repo Temporal Knowledge Graph  
**Processors:** OR1200, IBEX, MOR1KX, Marocchino  
**Database:** `ic-knowledge-graph-temporal` (OneShard) / Graph: `IC_Temporal_Knowledge_Graph`  
**Semantic Bridges:** 193 `RESOLVED_TO` + 61 `CROSS_REPO_SIMILAR_TO`  
**Entity Resolution:** Alias-aware exact match + gated embeddings  
**Full Rebuild:** `scripts/rebuild_database.sh`  
**Last Updated:** March 2026

---

## For Developers

### Documentation Standards
- Use markdown (.md) for all documentation
- Include dates and status at the top of documents
- Keep filenames lowercase with hyphens (no spaces)
- Archive obsolete docs rather than deleting

### Where to Add New Docs
- Project docs → `project/`
- Reference materials → `reference/`
- Keep root `docs/` clean

### Updating This Index
When adding new major documentation, update this README with links.

---

## Contact

**Project:** IC Temporal Knowledge Graph — Multi-repo RISC Processor Demo  
**Repository:** github.com:ArthurKeen/ic-knowledge-graph.git
