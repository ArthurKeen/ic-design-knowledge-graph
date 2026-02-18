# IC Knowledge Graph — Business Requirements for Graph Analytics

**Purpose:** Domain description and business requirements for driving graph analytics and reporting on the IC Knowledge Graph via the agentic-graph-analytics.  
**Audience:** Business analysts, hardware engineers, data scientists, product managers.  
**Input For:** agentic-graph-analytics (graph analytics and reporting).

---

## Domain Description

### 1. Industry & Business Context

**Integrated Circuit (IC) Electronic Design Automation (EDA)** — semiconductor design and verification. The IC Knowledge Graph serves organizations that design, verify, and maintain digital hardware (RTL/ASIC/FPGA). This includes semiconductor companies, aerospace/defense contractors, research institutions, and IP vendors.

**Business Model:** Internal tooling and knowledge management for hardware engineering teams. The graph supports design traceability, verification, compliance, and knowledge transfer—reducing design cycle time, rework, and documentation drift.

**Organizational Context:** The current implementation uses the **OR1200 RISC processor** (open-source OpenRISC reference design) as sample data. The architecture is designed to scale to proprietary IP blocks, SoC designs, and multi-project portfolios.

**What We Do:** We harmonize three disparate data silos—structured RTL (Verilog) code, temporal Git version history, and unstructured technical specifications (PDFs)—into a single queryable knowledge graph. The core value is the **Semantic Bridge** that links implementation (code) to design intent (specifications), enabling traceability, impact analysis, and AI-assisted design exploration.

---

### 2. Graph Structure Overview

*Domain context for analytics. The schema agent provides live structure; this section gives semantic meaning and business context.*

**Nodes (Vertex Collections):**

- **RTL_Module** (~100): Verilog modules representing hardware blocks (e.g., or1200_cpu, or1200_alu, or1200_dc_fsm). Hierarchical structure with top-level and sub-modules.
- **RTL_Port** (~1.5K): Module interface pins (input/output/inout). External connectivity points.
- **RTL_Signal** (~1.4K): Internal wires and registers. Dataflow and control paths within modules.
- **RTL_LogicChunk** (~1.5K): Behavioral units—always blocks, assign statements. Implements combinational and sequential logic.
- **RTL_Assign** (~1.3K): Assign statements. Source of DRIVES/READS_FROM dataflow edges.
- **FSM_StateMachine** (few): Extracted finite state machines (e.g., data cache controller, instruction cache, exception handler).
- **FSM_State** (~25): Individual states within FSMs. Control flow states.
- **RTL_Parameter** (~220): Design parameters and localparams. Configurable design constants.
- **RTL_Memory** (few): RAM/ROM arrays and register files. Memory structures.
- **MemoryPort** (few): Structured memory interfaces (addr, data, we). Links RTL_Memory to ports.
- **ClockDomain** (few): Clock domains and timing boundaries. CDC (Clock Domain Crossing) analysis.
- **BusInterface** (~20): Logical bus groupings (Wishbone, SPR, LSU). Protocol interfaces.
- **Operator** (~200): Arithmetic and logical operators (adders, multiplexers). Resource usage.
- **GitCommit** (~50): Version history nodes. Design evolution over time.
- **Author** (few): Hardware engineers/contributors. Expertise and ownership.
- **OR1200_Golden_Entities** (~4K): Canonical documentation entities (deduplicated). Spec concepts, registers, instructions, interfaces.
- **OR1200_Entities** (~6K): Raw entities from GraphRAG extraction (before consolidation into Golden).
- **OR1200_Chunks** (~200): Text blocks from specifications. Source documentation paragraphs.
- **OR1200_Documents** (few): Source PDF file references. Specification documents.
- **OR1200_Communities** (~500): Entity clusters from Leiden algorithm. Related spec concepts.

**Edges (Edge Collections):**

- **CONTAINS**: RTL_Module → RTL_Module, RTL_LogicChunk, GenerateBlock (hierarchy, encapsulation)
- **DEPENDS_ON**: RTL_Module → RTL_Module (instantiation dependencies, e.g., CPU depends on ALU)
- **HAS_PORT**, **HAS_SIGNAL**: RTL_Module → RTL_Port, RTL_Signal (interface and internal structure)
- **WIRED_TO**: RTL_Port → RTL_Port (structural connectivity, pin-to-pin wiring)
- **MODIFIED**: GitCommit → RTL_Module (which modules changed per commit)
- **AUTHORED**: Author → GitCommit (commit authorship)
- **MAINTAINS**: Author → RTL_Module (derived expertise: ≥3 commits or ≥20% of module commits)
- **RESOLVED_TO**: RTL_Module, RTL_Port, RTL_Signal → OR1200_Golden_Entities (**Semantic Bridge**—code-to-spec links)
- **REFERENCES**: RTL_LogicChunk → OR1200_Chunks (direct spec paragraph references)
- **HAS_FSM**, **HAS_STATE**, **TRANSITIONS_TO**: FSM structure and control flow (FSM_StateMachine → FSM_State → FSM_State)
- **STATE_REGISTER**: FSM_StateMachine → RTL_Signal (which signal holds state)
- **IMPLEMENTED_BY**: FSM_StateMachine → RTL_LogicChunk (implementing always block)
- **CLOCKED_BY**: RTL_Signal, RTL_LogicChunk → ClockDomain (timing dependency)
- **CROSSES_DOMAIN**: RTL_Signal → ClockDomain (CDC detection)
- **IMPLEMENTS**: RTL_Module → BusInterface (bus protocol implementation)
- **PART_OF_BUS**: RTL_Port, RTL_Signal → BusInterface, MemoryPort (bus grouping)
- **DRIVES**, **READS_FROM**: RTL_Assign → RTL_Signal (dataflow: what drives/reads each signal)
- **HAS_PARAMETER**, **HAS_MEMORY**, **OVERRIDES**: RTL_Module → RTL_Parameter, RTL_Memory (design parameters)
- **ACCESSES**: RTL_LogicChunk → RTL_Memory (memory read/write)
- **MEMORY_PORT**: RTL_Memory → MemoryPort (memory interface)
- **USES_OPERATOR**: RTL_LogicChunk, RTL_Signal → Operator (resource usage)
- **OR1200_Golden_Relations**: OR1200_Golden_Entities ↔ OR1200_Golden_Entities (consolidated entity-to-entity relationships in documentation)
- **OR1200_Relations**: OR1200_Entities ↔ OR1200_Entities, OR1200_Chunks, OR1200_Communities (raw entity relationships before consolidation)
- **CONSOLIDATES**: OR1200_Golden_Entities → OR1200_Entities (entity resolution: Golden merges raw entities)

**Graph & Database:** `IC_Knowledge_Graph` in database `ic-knowledge-graph`. Collection names are exact (e.g., `OR1200_Golden_Entities` not `Golden_Entities`). GraphRAG prefix `OR1200_` is configurable via `GRAPHRAG_PREFIX`.

**Scale (approximate):**

- **~17K vertices** total
- **~59K edges** total
- **~2.2K Semantic Bridge links** (RTL → documentation)
- **~75% port coverage**, **~66% signal coverage** (RTL elements resolved to specs)
- **Sub-200ms** traversal queries for multi-hop traversals
- **~50 commits** of design history (OR1200)
- **~7 specification documents** (PDFs) ingested via GraphRAG

---

### 3. Domain-Specific Terminology

- **RTL (Register Transfer Level):** Hardware description at the register-transfer abstraction. Verilog/VHDL code representing digital logic before synthesis.
- **Semantic Bridge:** Automated links between RTL elements (modules, ports, signals) and documentation entities. Enables spec-to-code traceability without manual search.
- **Golden Entity:** Canonical, deduplicated concept from documentation after entity resolution. Merges raw extracted entities (e.g., "ALU" and "Arithmetic Logic Unit").
- **Bus Factor:** Number of engineers who understand/maintain a module. Bus Factor = 1 indicates single-maintainer risk (knowledge concentration).
- **CDC (Clock Domain Crossing):** Signal crossing between different clock domains. Requires synchronization; CDC bugs cause metastability.
- **FSM (Finite State Machine):** Control logic with discrete states and transitions. Extracted from state registers and case statements.
- **Traceability:** Ability to trace a requirement or spec concept to its implementation (and vice versa). Core compliance and verification need.
- **Design Drift:** Implementation diverging from documented specifications over time. Semantic Bridge helps detect and prevent drift.
- **Entity Resolution:** Process of merging duplicate or synonymous entities (e.g., "MMU" and "Memory Management Unit") into canonical Golden Entities.
- **GraphRAG:** Graph-based retrieval augmented generation. Extracts entities and relationships from unstructured docs for graph storage.
- **Time-Travel Query:** Query that filters or traverses the graph by Git commit history to analyze design evolution.
- **IP Block:** Intellectual property—reusable hardware design unit (e.g., CPU core, cache, bus interface).
- **Spec-to-Code Gap:** Disconnect between what specifications say and what code implements. Semantic Bridge closes this gap.

---

### 4. Business Context & Goals

**Current Challenges:**

1. **Spec-to-Code Traceability:** Engineers spend hours searching for where a spec requirement is implemented. Vector search returns semantically similar but structurally unrelated content.
2. **Design Evolution Blind Spots:** No easy way to answer "Which specs were impacted when we changed the ALU in commit #48?" or "When did this module last match its documentation?"
3. **Knowledge Concentration Risk:** Critical IP blocks maintained by single engineers (Bus Factor = 1). Succession planning and onboarding are reactive.
4. **Token Inefficiency:** AI agents retrieve 10+ document chunks (~5K tokens) per query. Graph-guided retrieval can return 3 precise entities (~500 tokens)—10x reduction.
5. **Documentation Drift:** Specifications and implementation diverge over time. No automated way to detect or quantify drift.

**Strategic Goals:**

1. **Traceability at Scale:** Enable engineers to traverse from any spec concept to implementing RTL (and back) in seconds.
2. **Temporal Design Audit:** Support impact analysis—"What changed?" and "What specs are affected?"—across commits and authors.
3. **Knowledge Risk Mitigation:** Identify Bus Factor = 1 modules and generate knowledge transfer plans. Map author expertise to modules.
4. **AI-Assisted Design:** Reduce LLM token usage by 90% through graph-constrained retrieval. Improve answer precision.
5. **Compliance & Verification:** Support design reviews, audits, and certification by providing traceability evidence.

**Why This Matters:**

Hardware design cycles are long and expensive. Rework from spec-code mismatch, lost expertise, and manual traceability work add weeks to schedules. The IC Knowledge Graph reduces these costs by unifying code, specs, and history into a single queryable graph—enabling faster onboarding, proactive risk management, and precise AI assistance.

**Success Criteria:**

- Semantic Bridge coverage: >70% of ports and signals resolved to documentation
- Query performance: <200ms for multi-hop traversals
- Bus Factor analysis: Identify all single-maintainer modules
- Token savings: 10x reduction in retrieval context for agent queries
- Traceability: One-click path from spec entity to RTL implementation

---

### 5. Data Characteristics

- **Historical Depth:** Full Git history for OR1200 (48 commits). Design evolution from initial implementation through refinements.
- **Update Frequency:** Batch ETL from RTL repository and documentation. Pipeline: import → create graph → bridge → author/FSM extraction. Suitable for daily or on-demand refresh.
- **Data Quality:** High structural quality from Verilog parsing. Entity resolution achieves ~100% precision on validated samples; recall improved via acronym expansion and parent context.
- **Documentation Source:** PDF specifications converted to markdown chunks via Docling/pymupdf4llm. GraphRAG extracts entities and relations. OR1200 uses 7 PDFs (main spec, supplementary, Japanese spec).
- **Compliance:** No patient/financial PII. Hardware design data may be proprietary; graph supports air-gapped or restricted deployments.
- **Known Limitations:**
  - OR1200 is a reference design; production graphs may have 10–100x more nodes
  - FSM transition extraction is partial (9 transitions extracted; some case-based logic not fully parsed)
  - GraphRAG prefix (OR1200_) is configurable for multi-project use
- **Integration:** Feeds into ArangoDB Graph Visualizer, AI agents (LangGraph, etc.), and custom AQL queries. Exports support migration and reporting.

---

## Domain Description Checklist

### Required Elements
- [x] **Industry clearly stated** (IC EDA, semiconductor design)
- [x] **Business model described** (internal tooling, knowledge management)
- [x] **Node types listed** with approximate counts
- [x] **Edge types explained** with meanings
- [x] **Scale metrics provided** (vertices, edges, bridges, coverage)
- [x] **Business context included** (problems, goals)

### Highly Recommended
- [x] **Domain terms defined** (12 key terms)
- [x] **Quantified goals** (coverage %, token savings, query latency)
- [x] **Current challenges explained**
- [x] **Success criteria stated**

### Optional but Valuable
- [x] **Data characteristics** noted (depth, quality, compliance)
- [x] **Integration context** (visualizer, agents, AQL)
- [x] **Known limitations** documented

---

## Analytics Use Cases for Graph-Analytics-AI-Platform

The following use cases should be supported by graph analytics and reporting. Each describes the business need, the analytical approach, and the expected output for the IC EDA domain.

---

### 1. Influence & Centrality

**Business Need:** Design teams need to prioritize verification effort and refactoring. Not all modules are equal—some sit at the heart of the design and touch many others. Changes to these "hub" modules have outsized impact; bugs here propagate widely. Conversely, modules with few connections may be good candidates for isolation or replacement.

**Analytical Approach:** Apply PageRank, degree centrality, and betweenness centrality to the module graph (CONTAINS, DEPENDS_ON, WIRED_TO). Identify modules that are highly connected, sit on critical paths, or act as bridges between sub-systems.

**Expected Output:** Ranked list of "critical" modules by influence score. Reports highlighting potential single points of failure. Recommendations for where to focus verification, documentation, and knowledge transfer. Visualization of the module dependency backbone.

---

### 2. Community Detection

**Business Need:** Large designs are often organized into logical sub-systems (e.g., CPU core, cache hierarchy, bus fabric, peripherals). These boundaries may not align with file structure or team ownership. Understanding natural clusters helps with modularization, IP reuse, and team assignment. Author collaboration patterns also form implicit communities.

**Analytical Approach:** Run community detection algorithms (e.g., Leiden, Louvain) on module-module, entity-entity, or author-module graphs. Use edge weights from DEPENDS_ON, RESOLVED_TO, or MAINTAINS as appropriate.

**Expected Output:** Clusters of related modules, documentation entities, or author expertise areas. Reports showing which IP blocks form coherent units vs. which are tightly coupled across boundaries. Team boundary recommendations. Comparison of detected communities to existing organizational structure.

---

### 3. Path Analysis & Traceability

**Business Need:** Engineers and auditors need to answer "Where is requirement X implemented?" and "What spec does this RTL block satisfy?" Manual search is slow and error-prone. The Semantic Bridge (RESOLVED_TO, REFERENCES) encodes these links, but traversing multi-hop paths requires graph analytics.

**Analytical Approach:** Compute shortest paths, k-hop neighborhoods, and subgraph extraction between specification entities (Golden Entities, Chunks) and RTL elements (Modules, Ports, Signals, LogicChunks). Support bidirectional traversal: spec → code and code → spec.

**Expected Output:** Traceability path visualization (e.g., Spec Entity → Golden Entity → RTL_Module → RTL_Port → RTL_LogicChunk). Reports listing all RTL elements that implement a given spec concept. Coverage matrices showing which requirements map to which modules. Exportable traceability evidence for compliance and design reviews.

---

### 4. Temporal Analysis & Design Evolution

**Business Need:** Designs evolve over time. Understanding when modules changed, who changed them, and how churn correlates with risk is essential for release planning and post-mortems. "Which specs became invalid when we refactored the ALU?" is a temporal question.

**Analytical Approach:** Leverage GitCommit and MODIFIED edges. Compute module churn (commits per module over time windows), author impact (commits by author, modules touched), and temporal clustering (bursts of related changes). Filter traversals by commit timestamp or author.

**Expected Output:** Design evolution timeline. Module churn heatmaps. Author activity and impact reports. "Time-travel" queries: show graph state as of a specific commit. Impact analysis: given a commit or module change, list affected documentation entities and downstream modules.

---

### 5. Bus Factor & Expertise Mapping

**Business Need:** Knowledge concentration is a risk. Modules maintained by a single engineer create bus factor = 1—if that person leaves, the organization loses critical expertise. Succession planning and onboarding require knowing who knows what and where the gaps are.

**Analytical Approach:** Use MAINTAINS and AUTHORED edges. Compute bus factor per module (count of maintainers), expertise score per author-module pair (commit frequency, recency), and collaboration networks (authors who co-maintain modules).

**Expected Output:** Risk report listing single-maintainer modules with severity scores. Author-module expertise matrix. Collaboration network graph (who works with whom). Recommendations for knowledge transfer, documentation priorities, and hiring/onboarding focus. Bus factor trend over time.

---

### 6. Semantic Bridge Quality

**Business Need:** The Semantic Bridge (RESOLVED_TO) is the core value of the graph. Its quality—coverage, precision, and confidence—directly affects traceability and AI retrieval. Gaps (unresolved RTL or orphaned spec entities) indicate where bridging or documentation needs improvement.

**Analytical Approach:** Analyze RESOLVED_TO edges by source type (Module, Port, Signal), target entity type, and resolution score. Compute coverage metrics (e.g., % of ports resolved per module). Identify modules with low coverage, entities with no RTL links, and resolution score distributions.

**Expected Output:** Coverage dashboard by module type and hierarchy level. Resolution score distribution (high/medium/low confidence). Gap report: RTL elements with no spec link, spec entities with no RTL implementation. Recommendations for improving entity resolution (e.g., acronym expansion, new entity types). Quality trend over pipeline runs.

---

### 7. FSM Complexity & Verification

**Business Need:** Finite state machines control critical behavior (cache controllers, exception handling, memory queues). Complex FSMs with many states and transitions are harder to verify and more prone to bugs. Unreachable or dead-end states indicate design or extraction issues.

**Analytical Approach:** Traverse HAS_FSM, HAS_STATE, TRANSITIONS_TO. Compute state count, transition count, transitions-per-state ratio. Run reachability analysis from reset state. Identify states with no outgoing transitions (dead-ends) or no incoming paths (unreachable).

**Expected Output:** FSM complexity report (state count, transition density, cyclomatic complexity). List of unreachable and dead-end states with remediation suggestions. FSM visualization (state diagram). Comparison across FSMs for relative complexity. Integration with verification tooling (e.g., export for model checking).

---

### 8. Dataflow & Dependency Analysis

**Business Need:** Module dependencies form a directed graph. Deep dependency chains affect build order, synthesis time, and change impact. Circular dependencies are design errors. Critical paths (longest dependency chains) indicate design bottlenecks and integration risk.

**Analytical Approach:** Traverse DEPENDS_ON, CONTAINS, and dataflow edges (DRIVES, READS_FROM). Compute dependency depth, longest path, and strongly connected components (cycles). Build dependency tree visualization.

**Expected Output:** Module dependency depth report. Critical path identification (longest chain from leaf to root). Circular dependency detection and reporting. Impact analysis: "If we change module X, which modules are affected?" Build order recommendations. Dataflow diagrams for key paths.

---

### 9. Documentation Coverage & Spec-to-Code Gap

**Business Need:** Specifications describe what should be built; RTL implements it. Gaps occur when (a) spec entities have no RTL implementation (missing or undocumented code), or (b) RTL elements have no spec link (undocumented implementation). Both indicate traceability and compliance risk.

**Analytical Approach:** Compare Golden Entities and Chunks to RTL elements via RESOLVED_TO and REFERENCES. Identify entities with zero outbound RTL links (orphaned spec) and RTL elements with zero inbound spec links (orphaned code). Segment by module, entity type, and hierarchy level.

**Expected Output:** Spec-to-code gap matrix. List of documented-but-unimplemented spec concepts. List of implemented-but-undocumented RTL elements. Coverage trend over time. Prioritized recommendations for closing gaps (documentation vs. implementation work). Compliance readiness score.

---

### 10. Cross-Domain Analysis (CDC, Clocks, Buses)

**Business Need:** Clock domain crossings (CDC) require careful synchronization; unsynchronized CDC causes metastability and intermittent failures. Bus interfaces define protocol boundaries. Understanding clock domains, CDC signals, and bus usage is critical for timing closure and integration.

**Analytical Approach:** Traverse CLOCKED_BY, CROSSES_DOMAIN, IMPLEMENTS, PART_OF_BUS. Map signals to clock domains. Identify signals that cross domains (CDC). Aggregate bus interface usage by module. Detect modules that span multiple clock domains.

**Expected Output:** Clock domain map. CDC signal report (signals crossing domains, with synchronization status if available). Bus interface usage by module. Modules at domain boundaries (high CDC risk). Recommendations for CDC review and bus protocol compliance.

---

**Document Version:** 1.0  
**Last Updated:** February 13, 2026  
**Project:** ic-knowledge-graph  
**Target Platform:** agentic-graph-analytics
