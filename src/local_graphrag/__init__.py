"""
src/local_graphrag/__init__.py

Local GraphRAG pipeline for the IC temporal knowledge graph.
Replaces the ArangoDB AMP-dependent etl_graphrag.py with a fully local,
offline-capable pipeline.

Supports backends:
  - openai   (OpenAI API — gpt-4o)
  - ollama   (local Ollama — llama3.1:8b or similar)
"""

from .pipeline import LocalGraphRAGPipeline
from .chunker import chunk_document
from .extractor import extract_entities_and_relations
from .loader import load_to_arangodb

__all__ = [
    "LocalGraphRAGPipeline",
    "chunk_document",
    "extract_entities_and_relations",
    "load_to_arangodb",
]

__version__ = "0.1.0"
