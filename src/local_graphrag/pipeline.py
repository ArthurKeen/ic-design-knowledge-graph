"""
src/local_graphrag/pipeline.py — End-to-end local GraphRAG pipeline orchestrator.

Full pipeline:
    1. Chunk documents  (chunker.py)
    2. Extract entities + relations  (extractor.py)
    3. Detect communities  (community_detector.py)
    4. Load into ArangoDB  (loader.py)

Usage (module):
    from local_graphrag.pipeline import LocalGraphRAGPipeline

    pipeline = LocalGraphRAGPipeline(prefix="MOR1KX_", backend="ollama")
    pipeline.run(doc_dir="/path/to/docs")

Usage (CLI):
    python -m local_graphrag.pipeline \
        --doc-dir ./or1200/doc \
        --prefix OR1200_ \
        --backend ollama \
        [--doc-version openrisc1200_spec_v1.0] \
        [--dry-run]
"""

import os
import sys
import json
import hashlib
import argparse

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from arango import ArangoClient

from config import ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD
from config_temporal import ARANGO_DATABASE, LOCAL_GRAPHRAG_BACKEND

from local_graphrag.chunker import chunk_document
from local_graphrag.extractor import EntityExtractor
from local_graphrag.embedder import embed_entities
from local_graphrag.community_detector import detect_communities
from local_graphrag.loader import load_to_arangodb


_DOC_EXTENSIONS = {".pdf", ".txt", ".md", ".rst"}


def _discover_docs(doc_dir: str) -> list[str]:
    """Recursively find all supported document files in doc_dir."""
    docs = []
    for root, _, files in os.walk(doc_dir):
        for fname in sorted(files):
            if os.path.splitext(fname)[1].lower() in _DOC_EXTENSIONS:
                docs.append(os.path.join(root, fname))
    return docs


def _make_document_node(doc_path: str, prefix: str,
                        doc_version: str = None, source_commit: str = None) -> dict:
    key = f"{prefix}doc_{hashlib.md5(doc_path.encode()).hexdigest()[:12]}"
    return {
        "_key":         key,
        "label":        os.path.basename(doc_path),
        "path":         doc_path,
        "doc_version":  doc_version,
        "source_commit": source_commit,
    }


class LocalGraphRAGPipeline:
    """End-to-end local GraphRAG pipeline for IC document ingestion."""

    def __init__(
        self,
        prefix:           str   = "OR1200_",
        backend:          str   = None,
        model:            str   = None,
        chunk_size:       int   = None,
        overlap:          int   = None,
        doc_version:      str   = None,
        source_commit:    str   = None,
        valid_from_epoch: str   = None,
        embedding_backend: str  = "sentence_transformers",
    ):
        self.prefix            = prefix
        self.backend           = backend or LOCAL_GRAPHRAG_BACKEND
        self.model             = model
        self.chunk_size        = chunk_size
        self.overlap           = overlap
        self.doc_version       = doc_version
        self.source_commit     = source_commit
        self.valid_from_epoch  = valid_from_epoch
        self.embedding_backend = embedding_backend

        self.extractor = EntityExtractor(backend=self.backend, model=self.model)

    def _get_db(self):
        client = ArangoClient(hosts=ARANGO_ENDPOINT)
        return client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)

    def run(
        self,
        doc_dir:   str  = None,
        doc_paths: list[str] = None,
        dry_run:   bool = False,
    ) -> dict:
        """
        Run the full pipeline on a directory or explicit list of documents.

        Args:
            doc_dir:    Directory to scan for documents.
            doc_paths:  Explicit list of document paths (overrides doc_dir).
            dry_run:    If True, run all steps but skip ArangoDB writes.

        Returns:
            Summary dict: {chunks, entities, relations, communities, documents}
        """
        # Discover documents
        if doc_paths:
            docs = doc_paths
        elif doc_dir:
            docs = _discover_docs(doc_dir)
        else:
            raise ValueError("Either doc_dir or doc_paths must be provided.")

        if not docs:
            print("[pipeline] No documents found.")
            return {}

        print(f"\n[pipeline] === Local GraphRAG Pipeline ===")
        print(f"  Prefix   : {self.prefix}")
        print(f"  Backend  : {self.backend}")
        print(f"  Docs     : {len(docs)}")
        print(f"  DB       : {ARANGO_DATABASE} @ {ARANGO_ENDPOINT}")
        print(f"  Dry run  : {dry_run}\n")

        # ---- Step 1: Chunk all documents ----
        print("[pipeline] Step 1/4: Chunking documents …")
        all_chunks = []
        document_nodes = []

        for doc_path in docs:
            doc_node = _make_document_node(
                doc_path, self.prefix, self.doc_version, self.source_commit
            )
            document_nodes.append(doc_node)

            try:
                chunks = chunk_document(
                    doc_path,
                    doc_version=self.doc_version,
                    source_commit=self.source_commit,
                    valid_from_epoch=self.valid_from_epoch,
                    chunk_size=self.chunk_size,
                    overlap=self.overlap,
                    prefix=self.prefix,
                )
                # Tag each chunk with its document _key
                for c in chunks:
                    c["document_key"] = doc_node["_key"]
                all_chunks.extend(chunks)
            except Exception as e:
                print(f"  [pipeline] WARNING: could not chunk {doc_path}: {e}")

        print(f"  Total chunks: {len(all_chunks)}\n")

        # ---- Step 2: Extract entities + relations ----
        print("[pipeline] Step 2/5: Extracting entities and relations …")
        all_entities, all_relations = self.extractor.extract_from_chunks(
            all_chunks, prefix=self.prefix
        )

        # ---- Step 3: Embed entities ----
        print(f"\n[pipeline] Step 3/5: Generating entity embeddings ({self.embedding_backend}) …")
        all_entities = embed_entities(all_entities, backend=self.embedding_backend)

        # ---- Step 4: Community detection ----
        print("\n[pipeline] Step 4/5: Detecting communities …")
        communities = detect_communities(all_entities, all_relations, prefix=self.prefix)

        # ---- Step 5: Load into ArangoDB ----
        print("\n[pipeline] Step 5/5: Loading into ArangoDB …")
        summary = {
            "chunks":      len(all_chunks),
            "entities":    len(all_entities),
            "relations":   len(all_relations),
            "communities": len(communities),
            "documents":   len(document_nodes),
        }

        if not dry_run:
            db = self._get_db()
            load_to_arangodb(
                entities=all_entities,
                relations=all_relations,
                communities=communities,
                chunks=all_chunks,
                documents=document_nodes,
                prefix=self.prefix,
                db=db,
            )
        else:
            print("  [pipeline] DRY RUN — skipping ArangoDB writes.")

        print(f"\n[pipeline] === Pipeline Complete ===")
        for k, v in summary.items():
            print(f"  {k:15s}: {v:6d}")

        return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Local GraphRAG pipeline — chunk, extract, detect communities, load"
    )
    parser.add_argument("--doc-dir",      help="Directory containing documents")
    parser.add_argument("--doc-path",     action="append", dest="doc_paths",
                        help="Explicit document path (repeat for multiple)")
    parser.add_argument("--prefix",       default="OR1200_",
                        help="Repo prefix for collections (default: OR1200_)")
    parser.add_argument("--backend",      default=None,
                        help="LLM backend: openai or ollama (default: from .env)")
    parser.add_argument("--model",        default=None,
                        help="LLM model override")
    parser.add_argument("--doc-version",  default=None,
                        help="Document version label (e.g. openrisc1200_spec_v0.7)")
    parser.add_argument("--epoch",        default=None,
                        help="Design epoch label for temporal metadata")
    parser.add_argument("--commit",       default=None,
                        help="Source git commit SHA for this document version")
    parser.add_argument("--chunk-size",   type=int, default=None)
    parser.add_argument("--overlap",      type=int, default=None)
    parser.add_argument("--embedding-backend", default="sentence_transformers",
                        choices=["sentence_transformers", "openai"],
                        help="Embedding backend for entity vectors (default: sentence_transformers)")
    parser.add_argument("--dry-run",      action="store_true")

    args = parser.parse_args()

    pipeline = LocalGraphRAGPipeline(
        prefix=args.prefix,
        backend=args.backend,
        model=args.model,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        doc_version=args.doc_version,
        source_commit=args.commit,
        valid_from_epoch=args.epoch,
        embedding_backend=args.embedding_backend,
    )

    pipeline.run(
        doc_dir=args.doc_dir,
        doc_paths=args.doc_paths,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
