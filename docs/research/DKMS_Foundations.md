# Research Foundations: Design Knowledge Management System (DKMS)

This project builds upon historical research into **Design Knowledge Management Systems (DKMS)**, specifically the work performed for the **Air Force Materiel Command** in the early 1990s.

## Historical Context

This project draws from two seminal research reports co-authored by **Arthur A. Keen** for the Air Force:

1.  **[Design Knowledge Management System (DKMS)](https://apps.dtic.mil/sti/tr/pdf/ADA230266.pdf)** (Phase I Final Report)
    *   **Date**: December 1990
    *   **Focus**: Established the foundational vision for an "Ideal Integrated Product Development Environment" and the conceptual architecture for capturing design rationale.
2.  **[Design Knowledge Management System (DKMS) Beta Test Report](https://apps.dtic.mil/sti/tr/pdf/ADA261453.pdf)** (Phase II Interim Report)
    *   **Date**: November 1992
    *   **Focus**: Detailed the practical application, prototyping, and industry beta testing of the DKMS subsystems (Integration Platform, Container Object System, etc.).

3.  **[Design Knowledge Management System (DKMS) Technology Impact Report](https://www.researchgate.net/publication/235129389_Design_Knowledge_Management_System_DKMS_Technology_Impact_Report)**
    *   **Date**: February 1992
    *   **Focus**: Analyzed the strategic impact of DKMS on engineering cycle time, redesign reduction, and the capture of life-cycle experience (MR&M - Manufacturability, Reliability, and Maintainability).

**Authors**: Richard J. Mayer, **Arthur A. Keen**, Matthew A. Grisius, Thomas M. Blinn, Jeffery C. Lockledge, David C. Browne, Les Sanders.  
**Agency**: Armstrong Laboratory, Logistics Research Division, Air Force Materiel Command.

## Relevance to the IC Design Knowledge Graph

The concepts pioneered in these DKMS reports provide the theoretical and functional foundations for the modern Integrated Circuit (IC) Design Knowledge Graph:

### 1. The Semantic Bridge (Knowledge Flow)
The DKMS report identified the need for "access to a trace of the decision rationale that led to the most current state of the product or process definition."
*   **Modern Implementation**: The `RESOLVED_TO` edges in this project act as the "Semantic Bridge," connecting structured RTL code back to the original design intent captured in unstructured specifications via GraphRAG.

### 2. Composite Objects & Granularity
The **Container Object System (COS)** in DKMS proposed a representation that was "recursive under composition, thus enabling instantiation of a group of objects as an entity."
*   **Modern Implementation**: Our RTL graph hierarchy (`Module` -> `LogicChunk` -> `Signal`) follows this exact principle of part-level granularity and isomorphic relationships across instances.

### 3. Design Evolution & History
DKMS discussed a **Design History Manager** to track the "rationale, experience, and knowledge bases" as decisions are made.
*   **Modern Implementation**: Integration with **Git history** enables "Time-Travel" queries, allowing engineers to audit design evolution and requirement validity across commits—a direct realization of the DKMS vision for managing life-cycle engineering knowledge.

### 4. Concurrent Engineering (CE) Support
DKMS was designed as an "integrated concurrent engineering system" to support rapid experimentation and prototyping.
*   **Modern Implementation**: By harmonizing disparate data silos (RTL, Docs, Git) into a single queryable graph, this project reduces communication bottlenecks between design, verification, and maintenance teams, accelerating the IC design lifecycle.

### 5. Capturing Design Intent (Rationale)
A core thrust of DKMS was capturing "Model rationale and knowledge-base capture" to ensure expertise is preserved over long life-cycles.
*   **Modern Implementation**: The "Bus Factor" analysis and expertise mapping (`Author` -> `MAINTAINS` -> `Module`) identify knowledge risks and provide a roadmap for knowledge transfer, directly addressing the "life-cycle engineering knowledge assistance" requirements identified in the 1992 report.

### 6. Strategic Technology Impact (MR&M)
The **Technology Impact Report** forecasted significant reductions in redesign and engineering change requests by delivering lifecycle experience to initial designers.
*   **Modern Implementation**: Our "RTL Semantic Search" and documentation bridging provide a proactive "Design-for-X" (DfX) environment. By surfacing reliability and maintainability constraints (from the spec) directly alongside the implementation (the code), we reduce the expensive rework cycles that the DKMS impact report aimed to eliminate.

## Summary
The IC Design Knowledge Graph demo represents a "Production-Ready" realization of the DKMS vision, leveraging modern technologies like **ArangoDB**, **GraphRAG**, and **AQL** to solve the same fundamental challenges—knowledge capture, semantic bridging, and lifecycle management—identified by the Air Force research team over 35 years ago.
