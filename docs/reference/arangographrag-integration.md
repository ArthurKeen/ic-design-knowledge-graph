# OR1200 POC - ArangoGraphRAG Integration
Output: A plan for adapting this code base to work with the graphRAG imported elements.

The ArangoGraphRAG implementation divides documents into chunks (..._Chunks), identifies entities (..._Entities) in the chunks, performs entity resolution on the imported entities, identifies relationships (...Relationships), and identifies communities (..._Communities) using the Leiden algorithm. Embeddings are added to Entities and are optional on Chunks. The entities and relationships are represented using an LPG pattern with a type field on entity and relationship collections. The collections stored in the database are prepended with the project name (currently 'OR1200_'). The _Relations collection also represents the edges from Documents to Chunks and from Entities to Communities.

![alt text](image-2.png)


![alt text](image-1.png)

# Entity Resolution - semantic bridge
Output An analysis of options and a plan for developing a semantic bridge between the RTL_Modules and the GraphRAG imported entities.
During discusssions with the AI team, the consensus was that it would be better to use lexical analysis for entity resolution between the RTL_Modules and the GraphRAG imported entities.  The rationale for this strategy is that they believe the information on the modules is not sufficient to create embeddings that are comparable to those on the graphRAG entities.  Please ananlyze this yourself and let me know what you think
For the lexical analysis strategy we could use the ArangoSearch feature in Arango (t may be possible to use the Arango Entity Resolution Library which implements record blocking and lexical analysis. ) to do this lexical analysis or use a custom lexical analysis function.  The Arango Entity Resolution Library is based on the open source library 'entity-resolution' which is available on github at https://github.com/ArthurKeen/arango-entity-resolution and is also present in the local ~/code/arango-entity-resolution directory. 