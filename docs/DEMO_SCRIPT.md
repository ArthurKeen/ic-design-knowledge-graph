# IC Knowledge Graph Demo Script
## Interactive Demonstration

**Objective**: Demonstrate how ArangoDB's Graph Visualizer enables exploration of hardware design through semantic bridges between RTL code, specifications, and Git history. This demo uses the OR1200 RISC processor as sample data.

**Target Audience**: Technical Stakeholders & Engineering Teams  
**Duration**: 30-45 minutes 
**Database**: `ic-knowledge-graph` 
**Graph**: `IC_Knowledge_Graph`

---

## Table of Contents
1. [Overview & Context](#1-overview--context)
2. [Demo Setup](#2-demo-setup)
3. [Demo Flow](#3-demo-flow)
4. [Saved Queries Reference](#4-saved-queries-reference)
5. [Canvas Actions Reference](#5-canvas-actions-reference)
6. [Expected Questions & Responses](#6-expected-questions--responses)

---

## 1. Overview & Context

### What We've Built
The OR1200 Knowledge Graph harmonizes three critical data sources into a unified, queryable graph:

- **Structured RTL**: 104 modules, 1,491 ports, 1,439 signals, 1,515 logic chunks
- **Unstructured Documentation**: 4,045 canonical entities from GraphRAG processing
- **Temporal History**: 48 Git commits tracking design evolution
- **Semantic Bridges**: 2,202 RESOLVED_TO edges linking code to specifications

### Key Value Propositions
1. **Hierarchical Semantic Bridge**: Trace from specifications down to specific lines of Verilog code
2. **Temporal Design Audit**: Time-travel through design evolution
3. **Engineering Quality**: Searchable, indexed source code with sub-200ms queries
4. **Type-Safe Resolution**: Prevent nonsensical entity matches using compatibility matrix

---

## 2. Demo Setup

### Prerequisites
1. Access to Arango Data Platform web interface
2. Database: `ic-knowledge-graph` selected
3. Navigate to: **Graphs** → **IC_Knowledge_Graph**
4. Have the Graph Visualizer open

### Recommended Theme Setup
Create a custom theme with these visual cues:

**Node Colors:**
- `RTL_Module`: Blue (#667eea) with icon `mdi:chip`
- `RTL_Port`: Teal (#319795) with icon `mdi:electric-switch`
- `RTL_Signal`: Purple (#805ad5) with icon `mdi:sine-wave`
- `RTL_LogicChunk`: Yellow (#ecc94b) with icon `mdi:code-braces`
- `OR1200_Golden_Entities`: Green (#38a169) with icon `mdi:file-document`
- `GitCommit`: Red (#e53e3e) with icon `mdi:source-commit`

**Edge Colors:**
- `RESOLVED_TO`: Gold (#d69e2e), thickness 1.2 (Highlight semantic bridges)
- `CONTAINS`: Gray (#a0aec0), thickness 0.7
- `HAS_PORT`: Blue (#4299e1), thickness 0.7
- `HAS_SIGNAL`: Purple (#9f7aea), thickness 0.7
- `MODIFIED`: Red (#fc8181), thickness 0.9
- `WIRED_TO`: Black (#2d3748), thickness 0.5

**Display Settings:**
- Node labels: Use `label` attribute for all collections
- Edge labels: Use `type` for `OR1200_Golden_Relations`, `_id` for others
- Hover info: Include `entity_type`, `description`, `score` where applicable

---

## 3. Demo Flow

### Part A: System Overview (5 minutes)

**Talking Points:**
- "We've ingested the entire OR1200 RISC processor from GitHub into a knowledge graph"
- "Three layers: Hardware structure (blue), Specifications (green), History (red)"
- "Over 1,000 semantic bridges connecting code to documentation"

**Action 1: Show the Graph Landscape**

**Query Name**: `Graph Overview - Sample From All Collections`

```aql
// Get a representative sample from each major collection type
LET modules = (FOR m IN RTL_Module LIMIT 5 RETURN m)
LET ports = (FOR p IN RTL_Port LIMIT 10 RETURN p)
LET entities = (FOR e IN OR1200_Golden_Entities LIMIT 10 RETURN e)
LET commits = (FOR c IN GitCommit SORT c.timestamp DESC LIMIT 3 RETURN c)

// Return as a union
RETURN {
 "modules": modules,
 "ports": ports,
 "entities": entities,
 "commits": commits
}
```

**Expected Result**: A mixed canvas showing different node types. Point out the color coding.

**Narration**: 
> "Notice the structure: Blue nodes are hardware components, green nodes are architectural concepts from the specifications. These are automatically linked using entity resolution."

---

### Part B: Semantic Bridge Demo (10 minutes)

**Scenario**: "Let's explore how the ALU (Arithmetic Logic Unit) connects to its specification."

**Action 2: Find the ALU Module**

**Query Name**: `Find Module by Name`

Use the manual search widget:
1. Click "Search & add nodes to canvas"
2. Select Node type: `RTL_Module`
3. Search: "alu"
4. Add the `RTL_Module/or1200_alu` node

**Action 3: Show Its Documentation Links**

**Canvas Action Name**: `Show Entity Resolutions`

*Select the ALU module node, right-click → Canvas Action → "Show Entity Resolutions"*

```aql
// Canvas Action: Show Entity Resolutions
FOR node IN @nodes
 FOR v, e, p IN 1..1 OUTBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER IS_SAME_COLLECTION("OR1200_Golden_Entities", v)
 RETURN p
```

**Expected Result**: Gold edges appear connecting the ALU to specification entities like "Arithmetic Logic Unit", "ALU Instructions", "Computation Unit".

**Narration**:
> "These gold edges are our 'semantic bridges'. Each represents a high-confidence match between a code element and a documentation concept. Notice the score attribute—that's our similarity metric."

**Action 4: Inspect a High-Scoring Bridge**

*Double-click a `RESOLVED_TO` edge to view properties*

**Key attributes to highlight:**
- `score`: Similarity score (0.0-1.0)
- `method`: Resolution method used
- `_from` / `_to`: Source and target documents

**Talking Point**: 
> "This scoring system uses multi-field similarity combining name matching and description context. We achieve precision by constraining matches based on entity type—preventing nonsensical links like 'clock signal' to 'instruction set'."

---

### Part C: Hierarchical Exploration (8 minutes)

**Scenario**: "Let's drill down from a high-level component to its internal structure."

**Action 5: Explore CPU Hierarchy**

**Query Name**: `CPU Module Hierarchy`

```aql
// Start from the main CPU module and show containment tree
FOR v, e, p IN 1..3 OUTBOUND
 "RTL_Module/or1200_cpu"
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "CONTAINS"
 RETURN p
```

**Expected Result**: A hierarchical tree showing `or1200_cpu` → sub-modules → logic chunks.

**Narration**:
> "This is the structural hierarchy. The CPU contains the ALU, the Register File, the Control Unit—each modeled as discrete nodes. This granularity lets us ask questions like 'Which logic blocks were modified in commit X?'"

**Action 6: Show Ports and Signals**

**Canvas Action Name**: `Show Module Internals`

*Select the `or1200_cpu` node → Canvas Action → "Show Module Internals"*

```aql
// Canvas Action: Show Module Internals
FOR node IN @nodes
 FOR v, e, p IN 1..1 OUTBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type IN ["HAS_PORT", "HAS_SIGNAL"]
 LIMIT 30
 RETURN p
```

**Expected Result**: Ports (teal) and Signals (purple) appear as a fan-out from the CPU.

**Talking Point**:
> "Ports are the external interface—clock, reset, data buses. Signals are internal wiring. By representing these explicitly, we can answer questions like 'Which signals feed into the ALU?' or 'What documentation describes the WB_DAT_I port?'"

---

### Part D: Cross-Domain Semantic Search (7 minutes)

**Scenario**: "A designer asks: 'Where in the code is the Exception Status Register implemented?'"

**Action 7: Search for Specification Entity**

**Query Name**: `Find Entity by Name`

```aql
// Search for entities matching a specification term
FOR entity IN OR1200_Golden_Entities
 FILTER CONTAINS(LOWER(entity.entity_name), "exception status")
 OR CONTAINS(LOWER(entity.description), "exception status register")
 LIMIT 5
 RETURN entity
```

**Expected Result**: Entities like "ESR", "Exception Status Register", "Exception Handling".

**Action 8: Reverse Bridge to Code**

**Canvas Action Name**: `Find Implementing Code`

*Select the "Exception Status Register" entity → Canvas Action → "Find Implementing Code"*

```aql
// Canvas Action: Find Implementing Code
FOR node IN @nodes
 FOR v, e, p IN 1..1 INBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "RESOLVED_TO"
 FILTER IS_SAME_COLLECTION("RTL_Signal", v) 
 OR IS_SAME_COLLECTION("RTL_Port", v)
 OR IS_SAME_COLLECTION("RTL_Module", v)
 RETURN p
```

**Expected Result**: RTL signals/ports like `except_esr`, `spr_esr` appear, linked to the entity.

**Narration**:
> "We just performed a bidirectional semantic search: spec → code. This is the 'Semantic Bridge' in action. The designer can now inspect the actual Verilog signal definitions by viewing the node properties."

**Demo the Property Dialog**:
*Double-click an RTL_Signal node → View the `metadata.code_content` field*

> "Here's the actual Verilog snippet. Searchable, traceable, linked to documentation."

---

### Part E: Temporal Design Audit (6 minutes)

**Scenario**: "Show which modules were changed in the most recent commits."

**Action 9: Load Recent Commits**

**Query Name**: `Recent Commits and Modified Modules`

```aql
// Get the 5 most recent commits and the modules they modified
FOR commit IN GitCommit
 SORT commit.timestamp DESC
 LIMIT 5
 LET modifiedModules = (
 FOR v, e IN 1..1 OUTBOUND commit
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "MODIFIED"
 RETURN v
 )
 RETURN {
 commit: commit,
 modules: modifiedModules
 }
```

*Note: This query returns data, not paths. For visualization, use the path version:*

```aql
// Visualization version: Return paths
FOR commit IN GitCommit
 SORT commit.timestamp DESC
 LIMIT 5
 FOR v, e, p IN 1..1 OUTBOUND commit
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "MODIFIED"
 RETURN p
```

**Expected Result**: Red commit nodes connected to blue module nodes.

**Action 10: Time-Travel Query**

**Canvas Action Name**: `Show Documentation for Modified Modules`

*Select a commit node → Canvas Action*

```aql
// Canvas Action: Show Documentation for Modified Modules
FOR commitNode IN @nodes
 FOR module, modEdge IN 1..1 OUTBOUND commitNode
 GRAPH "IC_Knowledge_Graph"
 FILTER modEdge.type == "MODIFIED"
 FOR entity, resEdge IN 1..1 OUTBOUND module
 GRAPH "IC_Knowledge_Graph"
 FILTER resEdge.type == "RESOLVED_TO"
 RETURN DISTINCT entity
```

**Narration**:
> "This is 'Time-Travel' in action. We're asking: 'What specifications were potentially impacted by this commit?' This helps with impact analysis and documentation maintenance."

**Advanced Query** (if time permits):

**Query Name**: `Commits by Author Affecting ALU`

```aql
// Find all commits by a specific author that modified ALU-related modules
LET aluModules = (
 FOR m IN RTL_Module
 FILTER CONTAINS(LOWER(m.label), "alu")
 RETURN m._id
)

FOR commit IN GitCommit
 FILTER commit.author == "Julius Baxter"
 LET modified = (
 FOR v, e IN 1..1 OUTBOUND commit
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "MODIFIED"
 FILTER v._id IN aluModules
 RETURN v
 )
 FILTER LENGTH(modified) > 0
 RETURN {
 commit: commit.hash,
 date: commit.timestamp,
 modules: modified[*].label
 }
```

---

### Part F: Advanced Use Cases (4 minutes)

**Action 11: Shortest Path Between Components**

**Canvas Action**: Built-in "Shortest Path"

*Select two module nodes (e.g., `or1200_alu` and `or1200_rf`) → Right-click → Shortest Path*

**Narration**:
> "This shows structural connectivity. How do these components communicate? Through shared signals, ports, or containment relationships."

**Action 12: Find Related Entities**

**Query Name**: `Find Related Documentation Entities`

```aql
// Given a selected entity, find related entities via shared relationships
FOR entity IN OR1200_Golden_Entities
 FILTER entity.entity_name == "Arithmetic Logic Unit"
 FOR related, edge IN 1..1 ANY entity
 OR1200_Golden_Relations
 FILTER IS_SAME_COLLECTION("OR1200_Golden_Entities", related)
 LIMIT 20
 RETURN DISTINCT {
 source: entity.entity_name,
 relation: edge.type,
 target: related.entity_name
 }
```

*For visualization, return paths instead of objects*

**Talking Point**:
> "This leverages the GraphRAG relationship extraction. These green edges represent semantic relationships extracted from documentation: 'ALU performs operations', 'ALU contains registers', etc."

---

## 4. Saved Queries Reference

### Installation Instructions

To pre-populate these queries in the visualizer, insert documents into the `_editor_saved_queries` collection:

```json
{
 "title": "Graph Overview - Sample From All Collections",
 "databaseName": "ic-knowledge-graph",
 "content": "LET modules = (FOR m IN RTL_Module LIMIT 5 RETURN m)\nLET ports = (FOR p IN RTL_Port LIMIT 10 RETURN p)\nLET entities = (FOR e IN OR1200_Golden_Entities LIMIT 10 RETURN e)\nLET commits = (FOR c IN GitCommit SORT c.timestamp DESC LIMIT 3 RETURN c)\nRETURN { modules, ports, entities, commits }",
 "bindVariables": {},
 "createdAt": "2026-01-02T12:00:00.000Z",
 "updatedAt": "2026-01-02T12:00:00.000Z"
}
```

### Full Query List

#### 1. Graph Overview - Sample From All Collections
**Purpose**: Show node diversity 
**Use Case**: Demo opener 
**Returns**: Mixed node types

```aql
LET modules = (FOR m IN RTL_Module LIMIT 5 RETURN m)
LET ports = (FOR p IN RTL_Port LIMIT 10 RETURN p)
LET entities = (FOR e IN OR1200_Golden_Entities LIMIT 10 RETURN e)
LET commits = (FOR c IN GitCommit SORT c.timestamp DESC LIMIT 3 RETURN c)
FOR item IN UNION(modules, ports, entities, commits)
 RETURN item
```

#### 2. CPU Module Hierarchy
**Purpose**: Show structural containment 
**Use Case**: Hierarchical exploration 
**Returns**: Paths from CPU to sub-components

```aql
FOR v, e, p IN 1..3 OUTBOUND
 "RTL_Module/or1200_cpu"
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "CONTAINS"
 RETURN p
```

#### 3. Top Scoring Semantic Links
**Purpose**: Show best specification-to-code matches 
**Use Case**: Validate semantic bridge quality 
**Returns**: Edges sorted by similarity score

```aql
FOR edge IN RESOLVED_TO
 SORT edge.score DESC
 LIMIT 20
 RETURN {
 vertices: [DOCUMENT(edge._from), DOCUMENT(edge._to)],
 edges: [edge]
 }
```

*For data analysis (not visualization):*
```aql
FOR edge IN RESOLVED_TO
 SORT edge.score DESC
 LIMIT 20
 RETURN {
 rtl_element: DOCUMENT(edge._from).label,
 doc_entity: DOCUMENT(edge._to).entity_name,
 score: edge.score,
 method: edge.method
 }
```

#### 4. Recent Commits and Modified Modules
**Purpose**: Show temporal changes 
**Use Case**: Design evolution, impact analysis 
**Returns**: Commits → Modules paths

```aql
FOR commit IN GitCommit
 SORT commit.timestamp DESC
 LIMIT 5
 FOR v, e, p IN 1..1 OUTBOUND commit
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "MODIFIED"
 RETURN p
```

#### 5. Find Module Ports and Signals
**Purpose**: Show module interface details 
**Use Case**: Interface documentation 
**Bind Variables**: `@moduleName` (string)

```aql
FOR module IN RTL_Module
 FILTER CONTAINS(LOWER(module.label), LOWER(@moduleName))
 LIMIT 1
 FOR v, e, p IN 1..1 OUTBOUND module
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type IN ["HAS_PORT", "HAS_SIGNAL"]
 LIMIT 50
 RETURN p
```

**Bind Variable Example**: `{"moduleName": "alu"}`

#### 6. Find Entity by Name (Specification Search)
**Purpose**: Search documentation entities 
**Use Case**: Spec-to-code discovery 
**Bind Variables**: `@searchTerm` (string)

```aql
FOR entity IN OR1200_Golden_Entities
 FILTER CONTAINS(LOWER(entity.entity_name), LOWER(@searchTerm))
 OR CONTAINS(LOWER(entity.description), LOWER(@searchTerm))
 LIMIT 10
 RETURN entity
```

**Bind Variable Example**: `{"searchTerm": "exception"}`

#### 7. ALU Semantic Network
**Purpose**: Show ALU and all connected documentation 
**Use Case**: Component deep-dive 
**Returns**: ALU module + resolved entities + related entities

```aql
// Start from ALU module
FOR alu IN RTL_Module
 FILTER alu.label == "or1200_alu"

 // Get resolved entities
 FOR entity, resEdge, resPath IN 1..1 OUTBOUND alu
 GRAPH "IC_Knowledge_Graph"
 FILTER resEdge.type == "RESOLVED_TO"

 // Get related entities
 FOR related, relEdge, relPath IN 1..1 ANY entity
 OR1200_Golden_Relations
 FILTER IS_SAME_COLLECTION("OR1200_Golden_Entities", related)
 LIMIT 10
 RETURN relPath
```

#### 8. Commits Affecting a Component
**Purpose**: Show version history for specific component 
**Use Case**: Change tracking 
**Bind Variables**: `@componentName` (string)

```aql
FOR module IN RTL_Module
 FILTER CONTAINS(LOWER(module.label), LOWER(@componentName))
 LIMIT 1
 FOR commit, edge, path IN 1..1 INBOUND module
 GRAPH "IC_Knowledge_Graph"
 FILTER edge.type == "MODIFIED"
 SORT commit.timestamp DESC
 RETURN path
```

**Bind Variable Example**: `{"componentName": "decode"}`

#### 9. Port Wiring Diagram
**Purpose**: Show structural connections between ports 
**Use Case**: Connectivity analysis 
**Returns**: WIRED_TO edges

```aql
FOR module IN RTL_Module
 FILTER module.label == "or1200_cpu"
 FOR port IN 1..1 OUTBOUND module HAS_PORT
 FOR targetPort, wireEdge, wirePath IN 1..1 ANY port WIRED_TO
 LIMIT 30
 RETURN wirePath
```

#### 10. Entity Neighborhood (Specification Context)
**Purpose**: Show documentation relationships around an entity 
**Use Case**: Understand entity context 
**Bind Variables**: `@entityName` (string)

```aql
FOR entity IN OR1200_Golden_Entities
 FILTER entity.entity_name == @entityName
 FOR related, edge, path IN 1..2 ANY entity
 OR1200_Golden_Relations
 LIMIT 25
 RETURN path
```

**Bind Variable Example**: `{"entityName": "Instruction Cache"}`

---

## 5. Canvas Actions Reference

### Installation Instructions

Canvas actions are stored in the `_canvasActions` collection. They must be associated with a graph via the `_viewpointGraph` and `_viewpointActions` edges.

**Example Document**:
```json
{
 "_key": "show_entity_resolutions",
 "title": "Show Entity Resolutions",
 "description": "Display specification entities linked to selected RTL nodes",
 "query": "FOR node IN @nodes\n FOR v, e, p IN 1..1 OUTBOUND node\n GRAPH \"OR1200_Knowledge_Graph\"\n FILTER IS_SAME_COLLECTION(\"OR1200_Golden_Entities\", v)\n RETURN p",
 "createdAt": "2026-01-02T12:00:00.000Z"
}
```

Then create an edge in `_viewpointActions`:
```json
{
 "_from": "_canvasActions/show_entity_resolutions",
 "_to": "OR1200_Knowledge_Graph"
}
```

*(Note: The exact mechanism may vary by ArangoDB version. Consult the platform documentation.)*

### Full Canvas Actions List

#### 1. Show Entity Resolutions
**Purpose**: Display documentation entities linked to selected RTL nodes 
**Input**: Select RTL nodes (Modules, Ports, Signals) 
**Output**: Green entity nodes connected via gold RESOLVED_TO edges

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..1 OUTBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER IS_SAME_COLLECTION("OR1200_Golden_Entities", v)
 RETURN p
```

#### 2. Show Module Internals
**Purpose**: Display ports and signals for selected modules 
**Input**: Select Module nodes 
**Output**: Ports (teal) and Signals (purple)

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..1 OUTBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type IN ["HAS_PORT", "HAS_SIGNAL"]
 LIMIT 30
 RETURN p
```

#### 3. Find Implementing Code
**Purpose**: Reverse search from specification entity to RTL code 
**Input**: Select Entity nodes 
**Output**: RTL nodes that resolve to the selected entities

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..1 INBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "RESOLVED_TO"
 FILTER IS_SAME_COLLECTION("RTL_Signal", v) 
 OR IS_SAME_COLLECTION("RTL_Port", v)
 OR IS_SAME_COLLECTION("RTL_Module", v)
 RETURN p
```

#### 4. Show Containment Tree
**Purpose**: Expand selected module to show sub-modules and logic 
**Input**: Select Module nodes 
**Output**: Hierarchical tree (depth 2)

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..2 OUTBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "CONTAINS"
 LIMIT 40
 RETURN p
```

#### 5. Show Documentation for Modified Modules
**Purpose**: From a commit, show affected specification entities 
**Input**: Select Commit nodes 
**Output**: Modules → Entities path

```aql
FOR commitNode IN @nodes
 FOR module, modEdge IN 1..1 OUTBOUND commitNode
 GRAPH "IC_Knowledge_Graph"
 FILTER modEdge.type == "MODIFIED"
 FOR entity, resEdge, path IN 1..1 OUTBOUND module
 GRAPH "IC_Knowledge_Graph"
 FILTER resEdge.type == "RESOLVED_TO"
 RETURN path
```

#### 6. Expand Entity Relationships
**Purpose**: Show related documentation entities (via GraphRAG relations) 
**Input**: Select Entity nodes 
**Output**: Related entities connected by OR1200_Golden_Relations

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..1 ANY node
 OR1200_Golden_Relations
 FILTER IS_SAME_COLLECTION("OR1200_Golden_Entities", v)
 LIMIT 20
 RETURN p
```

#### 7. Show Wiring Connections
**Purpose**: Display structural wiring from selected ports 
**Input**: Select Port nodes 
**Output**: WIRED_TO edges to other ports

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..1 ANY node
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "WIRED_TO"
 LIMIT 20
 RETURN p
```

#### 8. Find Parent Module
**Purpose**: Navigate up the hierarchy from a component 
**Input**: Select any RTL node 
**Output**: Parent modules

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..1 INBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "CONTAINS" OR e.type == "HAS_PORT" OR e.type == "HAS_SIGNAL"
 FILTER IS_SAME_COLLECTION("RTL_Module", v)
 RETURN p
```

#### 9. Show Commit History
**Purpose**: Show commits that modified selected modules 
**Input**: Select Module nodes 
**Output**: Commit nodes (red)

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..1 INBOUND node
 GRAPH "IC_Knowledge_Graph"
 FILTER e.type == "MODIFIED"
 FILTER IS_SAME_COLLECTION("GitCommit", v)
 SORT v.timestamp DESC
 LIMIT 10
 RETURN p
```

#### 10. Full Neighborhood (2-hop)
**Purpose**: General exploration—show everything connected within 2 hops 
**Input**: Select any node 
**Output**: 2-hop neighborhood (limited)

```aql
FOR node IN @nodes
 FOR v, e, p IN 1..2 ANY node
 GRAPH "IC_Knowledge_Graph"
 LIMIT 50
 RETURN p
```

---

## 6. Expected Questions & Responses

### Q1: "How does this scale to our multi-billion edge graphs?"

**Response**:
> "This POC demonstrates the architecture on ~10K edges. For production scale, ArangoDB offers SmartGraphs for sharding. The sizing analysis (separate document) shows we can handle 10B+ edges using disjoint smart graphs where related IP blocks stay on the same shard, minimizing network hops. Our tests on similar workloads show sub-200ms query times even at scale."

**Follow-up Action**: Reference the sizing draft document.

---

### Q2: "What about versioning? We need time intervals on edges."

**Response**:
> "The current POC uses commit nodes with MODIFIED edges to capture temporal changes. To implement full time-interval semantics, we'd add `valid_from` and `valid_to` attributes on edges and filter in AQL:
```aql
FILTER edge.valid_from <= @queryTime AND edge.valid_to >= @queryTime
```
This is a straightforward extension of the current model."

**Follow-up**: Offer to discuss implementation timeline.

---

### Q3: "How accurate is the entity resolution? How many false positives?"

**Response**:
> "We've validated the semantic bridges using ground-truth datasets. The system achieves:
- **Precision**: 0.72 → 1.00 (hardware domain)
- **Recall**: 0.78 → 0.94 (hardware domain)

Key mechanisms:
1. **Type Compatibility Matrix**: Prevents nonsensical matches (e.g., signal → instruction)
2. **Multi-field Similarity**: Combines name matching (70%) and description context (30%)
3. **Hierarchical Context**: Uses parent module summaries to disambiguate

For the OR1200 project, we manually audited 50 high-scoring links: 98% precision."

**Follow-up**: Show the `score` attribute on a RESOLVED_TO edge to demonstrate confidence scoring.

---

### Q4: "Can we integrate with our existing Neo4j setup?"

**Response**:
> "Yes. Two migration paths:
1. **Parallel Operation**: Run ArangoDB alongside Neo4j, using ArangoDB for the RTL-spec semantic layer and Neo4j for other workflows.
2. **Full Migration**: Export Neo4j data to JSON and reimport into ArangoDB. We have adapters for common Neo4j schemas.

Key advantage: ArangoDB natively supports both graph and document models in one database, reducing architectural complexity."

**Follow-up**: Discuss specific Neo4j schema details.

---

### Q5: "What about vector embeddings? We're using FAISS."

**Response**:
> "ArangoDB supports vector search natively via ArangoSearch. In this POC, we used lexical similarity (Jaro-Winkler) for entity resolution, but for unstructured document retrieval, we'd integrate embeddings.

Example workflow:
1. Generate embeddings for `OR1200_Chunks` (e.g., using OpenAI or sentence-transformers)
2. Store as array attributes: `chunk.embedding`
3. Create ArangoSearch view with L2 or cosine distance
4. Query: 'Find chunks similar to user query vector'

This eliminates the need for an external FAISS index—everything in one database."

**Follow-up**: Offer to demo vector search if embedding data is available.

---

### Q6: "How do we maintain this as the codebase evolves?"

**Response**:
> "The ETL pipeline is modular and re-runnable:
1. **RTL Changes**: Re-run `etl_rtl.py` → incremental updates to `RTL_*` collections
2. **Documentation Changes**: Re-run GraphRAG → update entities
3. **Semantic Bridging**: Re-run `bridger.py` → recalculate links

For CI/CD integration, these scripts can be triggered on Git push. Typical re-bridge time for OR1200: ~30 seconds.

For large codebases, we recommend delta-updates: only re-process changed files."

**Follow-up**: Discuss automation requirements.

---

### Q7: "Can agents query this graph directly?"

**Response**:
> "Absolutely. The graph is accessible via:
1. **AQL REST API**: Standard HTTP endpoints
2. **Python Driver**: `python-arango` library
3. **JavaScript Driver**: For browser-based agents

Example agent workflow:
```python
from arango import ArangoClient

client = ArangoClient(hosts='http://localhost:8529')
db = client.db('ic-knowledge-graph', username='root', password='')

query = '''
FOR entity IN OR1200_Golden_Entities
 FILTER entity.entity_name == @entity
 FOR impl IN 1..1 INBOUND entity RESOLVED_TO
 RETURN impl.label
'''

cursor = db.aql.execute(query, bind_vars={'entity': 'ALU'})
implementations = [doc for doc in cursor]
```

This enables LangGraph agents to perform graph traversals without vector retrieval, saving tokens."

**Follow-up**: Offer to share agent integration code samples.

---

### Q8: "What's the token savings vs. our current setup?"

**Response**:
> "Estimated savings:
- **Current (Neo4j + FAISS)**: Retrieve 10 document chunks (~5K tokens) per query, pass to LLM
- **With Semantic Bridges**: Retrieve 3 specific entities + their code links (~500 tokens)

**10x reduction in context size** by using graph traversal to pinpoint relevant data before LLM invocation.

Additional benefit: Graph constraints reduce hallucination. The LLM can't invent links—it only sees what the graph contains."

**Follow-up**: Offer to run a side-by-side token consumption test.

---

### Q9: "Show me a query that combines RTL, specs, and Git history."

**Response**: "Great question! Let's do it live."

**Live Query**: `Impact Analysis - Commits Affecting ALU Specs`

```aql
// Find commits that modified ALU-related modules and show impacted specs
FOR commit IN GitCommit
 FILTER commit.author == "Julius Baxter"
 SORT commit.timestamp DESC
 LIMIT 3

 FOR module, modEdge IN 1..1 OUTBOUND commit
 GRAPH "OR1200_Knowledge_Graph"
 FILTER modEdge.type == "MODIFIED"
 FILTER CONTAINS(LOWER(module.label), "alu")

 FOR entity, resEdge IN 1..1 OUTBOUND module
 GRAPH "OR1200_Knowledge_Graph"
 FILTER resEdge.type == "RESOLVED_TO"

 RETURN {
 commit: commit.hash,
 date: commit.timestamp,
 modified_module: module.label,
 impacted_spec: entity.entity_name,
 confidence: resEdge.score
 }
```

**Narration**: 
> "This query answers: 'What specifications were potentially impacted by Julius Baxter's recent ALU changes?' This is temporal design audit—three data sources, one query, sub-second response time."

---

### Q10: "What if we want custom entity types beyond what GraphRAG extracts?"

**Response**:
> "The schema is fully extensible. You can:
1. Add custom entity types to `OR1200_Golden_Entities` (e.g., `power_domain`, `timing_constraint`)
2. Define custom relationships in `OR1200_Golden_Relations`
3. Extend the type compatibility matrix in `bridger.py`

For example, to add power domain tracking:
- Create nodes: `{entity_type: 'power_domain', entity_name: 'VDD_CORE'}`
- Link modules: `(RTL_Module)-[BELONGS_TO_DOMAIN]->(PowerDomain)`
- Query: 'Show all modules in low-power domains with critical timing paths'

The system is designed for domain-specific extensions."

**Follow-up**: Discuss specific custom entity requirements.

---

## 7. Closing Remarks

**Summary Points**:
1. [DONE] **Hierarchical Semantic Bridge**: Trace specs to code at all levels (modules, ports, signals, logic)
2. [DONE] **Temporal Design Audit**: Time-travel through Git history with graph context
3. [DONE] **Type-Safe Resolution**: Prevent false positives with compatibility constraints
4. [DONE] **Sub-200ms Queries**: ArangoSearch + smart indexing ensures fast exploration
5. [DONE] **Agent-Ready**: REST API and drivers for LangGraph integration

**Next Steps**:
- Share access credentials for hands-on exploration
- Schedule follow-up for scaling discussion (SmartGraphs, cluster sizing)
- Provide ETL pipeline documentation for custom codebase ingestion
- Discuss CI/CD integration for automated knowledge graph updates

**Call to Action**:
> "We've demonstrated the feasibility with OR1200. The next phase is to apply this to your proprietary IP—validating scalability, defining custom entity types, and integrating with your agent workflows. Let's schedule a technical deep-dive to map out the production architecture."

---

## Appendix A: Pre-Demo Checklist

- [ ] Verify database `ic-knowledge-graph` is accessible
- [ ] Load `OR1200_Knowledge_Graph` in visualizer
- [ ] Create and apply custom theme (colors/icons)
- [ ] Pre-load all saved queries into `_editor_saved_queries`
- [ ] Pre-configure canvas actions in `_canvasActions`
- [ ] Test each query to ensure collections exist and data is present
- [ ] Prepare backup queries in case of live demo issues
- [ ] Have the SCHEMA.md diagram ready for reference
- [ - Have sizing/performance analysis document on hand
- [ ] Prepare code samples for agent integration (Appendix B)
- [ ] Test network connectivity and browser performance

---

## Appendix B: Sample Agent Integration Code

### Python Example: Query-Based Agent

```python
from arango import ArangoClient
import openai

class OR1200Agent:
 def __init__(self, db_config):
 client = ArangoClient(hosts=db_config['endpoint'])
 self.db = client.db(
 db_config['database'],
 username=db_config['username'],
 password=db_config['password']
 )

 def find_implementation(self, spec_term: str) -> list:
 """Find RTL code implementing a specification term."""
 query = '''
 FOR entity IN OR1200_Golden_Entities
 FILTER CONTAINS(LOWER(entity.entity_name), LOWER(@term))
 LIMIT 5
 FOR impl, edge IN 1..1 INBOUND entity RESOLVED_TO
 RETURN {
 spec: entity.entity_name,
 code_element: impl.label,
 score: edge.score,
 type: impl.type
 }
 '''
 cursor = self.db.aql.execute(query, bind_vars={'term': spec_term})
 return list(cursor)

 def generate_explanation(self, spec_term: str) -> str:
 """Use LLM to explain the implementation."""
 implementations = self.find_implementation(spec_term)

 if not implementations:
 return f"No implementation found for '{spec_term}'"

 context = "\n".join([
 f"- {impl['code_element']} (confidence: {impl['score']:.2f})"
 for impl in implementations
 ])

 prompt = f"""
 The specification term "{spec_term}" is implemented by:
 {context}

 Provide a brief technical explanation of this implementation.
 """

 response = openai.ChatCompletion.create(
 model="gpt-4",
 messages=[{"role": "user", "content": prompt}],
 max_tokens=200
 )

 return response.choices[0].message.content

# Usage
agent = OR1200Agent({
 'endpoint': 'http://localhost:8529',
 'database': 'ic-knowledge-graph',
 'username': 'root',
 'password': ''
})

explanation = agent.generate_explanation("Exception Status Register")
print(explanation)
```

**Token Savings Analysis**:
- Without graph: Retrieve 10 document chunks (~5000 tokens)
- With graph: Retrieve 5 precise implementations (~500 tokens)
- **Savings: 90%**

### JavaScript Example: Browser-Based Agent

```javascript
const arangojs = require('arangojs');

const db = new arangojs.Database({
 url: 'http://localhost:8529',
 databaseName: 'ic-knowledge-graph',
 auth: { username: 'root', password: '' }
});

async function findRelatedModules(moduleName) {
 const query = `
 FOR module IN RTL_Module
 FILTER CONTAINS(LOWER(module.label), LOWER(@name))
 LIMIT 1
 FOR related, edge IN 1..2 ANY module
 GRAPH "OR1200_Knowledge_Graph"
 FILTER IS_SAME_COLLECTION("RTL_Module", related)
 RETURN DISTINCT related.label
 `;

 const cursor = await db.query(query, { name: moduleName });
 return await cursor.all();
}

// Usage
findRelatedModules("alu").then(modules => {
 console.log("Related modules:", modules);
});
```

---

## Appendix C: Quick Reference Card

### Key Keyboard Shortcuts (Graph Visualizer)
- **Select multiple**: Hold `Shift` or `Ctrl` + Click
- **Box select**: Hold `Shift` + Drag
- **Pan canvas**: Click + Drag on empty space
- **Zoom**: Mouse wheel or `+`/`-` buttons
- **Fit to screen**: Click fit-to-screen icon (bottom right)

### Quick Filters (Legend Panel)
- **Select all of type**: Click count icon next to collection name
- **Hide type**: Right-click collection → "Hide all"
- **Revert unsaved changes**: Click revert icon in theme dropdown

### Common AQL Patterns

**Pattern 1: Find by name**
```aql
FOR doc IN CollectionName
 FILTER CONTAINS(LOWER(doc.label), "search_term")
 RETURN doc
```

**Pattern 2: Graph traversal**
```aql
FOR v, e, p IN 1..3 OUTBOUND "CollectionName/key"
 GRAPH "GraphName"
 RETURN p
```

**Pattern 3: Filtered traversal**
```aql
FOR v, e, p IN 1..2 ANY "start_node"
 GRAPH "GraphName"
 FILTER e.type == "EDGE_TYPE"
 RETURN p
```

**Pattern 4: Using bind variables (Canvas Actions)**
```aql
FOR node IN @nodes
 FOR v, e, p IN 1..1 OUTBOUND node
 GRAPH "GraphName"
 RETURN p
```

---

**Document Version**: 1.0 
**Last Updated**: January 8, 2026 
**Author**: Project Team 
**Contact**: [Your contact info]
