# Product Requirements Document: IC Knowledge Graph Demo

## Context

The source contains both structured and unstructured data. This PRD outlines an approach to ETL structured data into a Knowledge Graph and GraphRAG import unstructured data, harmonizing them in the same graph using Entity Resolution for cross-referencing. The source data for OR1200 is in a GitHub repository, allowing temporal analysis of design changes over time.

## Approach

This approach integrates GitHub commit history (temporal data) with harmonized RTL (structured) and Documentation (unstructured) graphs, addressing key requirements for versioning and "Semantic Bridges."

## Value Demonstration Strategy

The POC demonstrates value through addressing common challenges in hardware design knowledge management:

1. **Semantic Bridge & Retrieval Precision**
   - Challenge: Vector stores may retrieve semantically similar but structurally unrelated documentation
   - Solution: Graph traversal constraints from RTL nodes to documentation chunks
   - Benefit: Reduced token consumption and improved accuracy

2. **Time-Travel & Design Evolution**
   - Challenge: Tracking requirement validity across design changes
   - Solution: Git history integration enabling temporal queries
   - Example: "Show which requirements became invalid when ALU connectivity changed in Commit #48"

3. **Distributed Scale**
   - Challenge: Managing billions of edges in graph databases
   - Solution: Sharded clusters with SmartGraph traversal
   - Benefit: Keep related IP blocks on same shard to minimize network hops

4. **Knowledge Risk Mitigation**
   - Challenge: "Bus Factor" risks where critical IP is understood by only one engineer
   - Solution: Automated graph analysis of commit history to identify single points of failure
   - Benefit: Proactive succession planning and accelerated onboarding for new engineers

--------------------------------------------------------------------------------

## Product Requirements Document (PRD) for POC Demo

**Title**: "Hierarchical Semantic Bridge" & Temporal Graph Demo (Project OR1200)  
**Target Audience**: Technical Stakeholders & Engineering Teams  
**Objective**: Demonstrate how ArangoDB can harmonize fine-grained RTL, temporal version history, and professional-grade GraphRAG documentation into a single, queryable "Digital Twin" of hardware design.

### 1. Data Sources & Ingestion Strategy

**Structured Source (RTL)**: openrisc/or1200 GitHub Repository
- ETL Action: Decompose Verilog files into Modules, Ports, Signals, and Logic Chunks (always blocks/assigns)
- Graph Schema: `(Module)-[CONTAINS]->(SubModule/LogicChunk)`, `(Module)-[HAS_PORT]->(Port)`, `(Module)-[HAS_SIGNAL]->(Signal)`

**Unstructured Source (Docs)**: ArangoGraphRAG Output
- ETL Action: Integrate with collections: `OR1200_Entities`, `OR1200_Chunks`, and `OR1200_Documents`
- Graph Schema: `(Entities)-[MENTIONS]->(Chunks)`

**Temporal Source (Git)**: Full commit history
- ETL Action: Capture hash, author, and timestamp
- Graph Schema: `(Commit)-[MODIFIED]->(Module)`

### 2. Functional Requirements (The "Harmonization")

**Feature A: Hierarchical Semantic Bridge**
- Requirement: Link RTL elements at all levels (Modules, Ports, Signals, Logic) to Documentation
- Implementation: Use the Arango Entity Resolution Library and ArangoSearch to bridge technical identifiers against technical terms in the specification
- Results:
  - `(RTL_Module/Port/Signal) -[RESOLVED_TO]-> (OR1200_Golden_Entities)`
  - `(RTL_LogicChunk) -[REFERENCES]-> (OR1200_Chunks)`
- Value: Allows AI agents to trace a specification requirement down to the specific line of code or logic block that implements it

**Feature B: Temporal Design Audit**
- Requirement: Support "Time-Travel" queries that filter by graph structure and history
- User Story: "Show me the documentation entities associated with the modules modified by a specific author during the last ALU redesign"
- Technical: Graph traversal from `Commit -> Module -> Documentation Entity`

**Feature C: Engineering Quality & Searchability**
- Requirement: All source code must be searchable and indexed
- Implementation: Store Verilog `code_content` on nodes and create an ArangoSearch View for hybrid semantic/lexical retrieval

**Feature D: Knowledge Transfer & Risk Assessment**
- Requirement: Analyze human factors and organizational risks in the design lifecycle
- User Story: "Identify high-risk modules with a 'Bus Factor' of 1 (single maintainer) and generate a knowledge transfer plan for new hires"
- Technical: Analysis of `(Author)-[MAINTAINS]->(Module)` and `(Author)-[AUTHORED]->(Commit)` edges to calculate expertise scores and risk metrics
- Value: proactive identification of knowledge gaps and automated onboarding support

### 3. Success Metrics (Acceptance Criteria)

1. **Granularity**: Successful creation of >4,500 vertices and >4,800 edges representing the hardware's internal structure
2. **Bridge Coverage**: Resolve at least 250+ semantic links across the design hierarchy (Modules, Ports, and Signals)
3. **Knowledge Insight**: Successfully map author expertise to 100% of modules and identify at least 3 "Bus Factor 1" risks
4. **Searchability**: Retrieval of source code snippets directly from documentation-driven queries in under 200ms

### 4. Demonstration Visualization

The demo should demonstrate a visualization (using ArangoDB Graph Viewer) showing:

1. **Blue Nodes**: The RTL hierarchy (Modules, Ports, Signals)
2. **Yellow Nodes**: Logic Chunks (the behavioral implementation)
3. **Green Nodes**: Documentation Entities (requirements and specifications)
4. **Gold Edges**: The "Hierarchical Bridge" linking RTL to documentation
5. **Temporal Filter**: Filtering by commit history to watch the design evolve

## Value Proposition

This POC demonstrates how to unify code and specifications into a single queryable graph, enabling engineers to:
- Trace every line of code to its corresponding specification
- Track design evolution through Git history
- Ensure design never drifts from documented requirements
- Reduce LLM token usage through precise graph-based retrieval
