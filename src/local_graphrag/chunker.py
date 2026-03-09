"""
src/local_graphrag/chunker.py — Version-aware document chunker for the local GraphRAG pipeline.

Wraps the existing document_converter.py to produce paragraph/section chunks
with temporal metadata (doc_version, source_commit, valid_from_epoch).

Usage:
    from local_graphrag.chunker import chunk_document

    chunks = chunk_document(
        doc_path="or1200/doc/openrisc1200_spec.txt",
        doc_version="openrisc1200_spec_v0.7",
        chunk_size=1200,
        overlap=100,
    )
"""

import os
import sys
import re
import hashlib

# Allow running from either src/ or src/local_graphrag/
_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from config_temporal import LOCAL_GRAPHRAG_CHUNK_SIZE, LOCAL_GRAPHRAG_CHUNK_OVERLAP


def _sha_key(text: str, suffix: str = "") -> str:
    """Short deterministic key from content hash."""
    return hashlib.sha256((text + suffix).encode()).hexdigest()[:16]


def _split_into_words(text: str) -> list[str]:
    return text.split()


def _chunk_words(words: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Split a word list into overlapping chunks of ~chunk_size words."""
    chunks = []
    step = max(1, chunk_size - overlap)
    i = 0
    while i < len(words):
        chunk_words = words[i: i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += step
    return chunks


def _detect_section_header(text: str) -> str | None:
    """Try to extract a section header from the start of a text chunk."""
    lines = text.strip().splitlines()
    for line in lines[:5]:
        line = line.strip()
        # Markdown heading
        if re.match(r"^#{1,4}\s+.+", line):
            return line.lstrip("#").strip()
        # Numbered section (e.g. "1.2.3 Title")
        if re.match(r"^\d+(\.\d+)*\s+[A-Z]", line):
            return line
    return None


def _convert_to_text(doc_path: str) -> str:
    """
    Convert a document to plain text / markdown.
    Delegates to existing document_converter.py for PDFs;
    reads .txt / .md files directly.
    """
    ext = os.path.splitext(doc_path)[1].lower()

    if ext in {".txt", ".md", ".rst"}:
        with open(doc_path, "r", errors="replace") as f:
            return f.read()

    if ext == ".pdf":
        try:
            from document_converter import DocumentConverter
            converter = DocumentConverter(method="pymupdf")
            return converter.convert(doc_path)
        except Exception as e:
            print(f"[chunker] WARNING: PDF conversion failed ({e}), trying plain read")
            with open(doc_path, "rb") as f:
                return f.read().decode("utf-8", errors="replace")

    # Fallback: read as text
    with open(doc_path, "r", errors="replace") as f:
        return f.read()


def chunk_document(
    doc_path: str,
    doc_version: str = None,
    source_commit: str = None,
    valid_from_epoch: str = None,
    chunk_size: int = None,
    overlap: int = None,
    prefix: str = "",
) -> list[dict]:
    """
    Chunk a document into overlapping text segments with temporal metadata.

    Args:
        doc_path:         Absolute path to the document (PDF, txt, md).
        doc_version:      Human-readable version label (e.g. "openrisc1200_spec_v0.7").
        source_commit:    Git SHA if the doc was extracted from git history.
        valid_from_epoch: Named design epoch this doc version belongs to.
        chunk_size:       Target chunk size in words (default from config).
        overlap:          Word overlap between consecutive chunks (default from config).
        prefix:           Repo prefix for _key namespacing (e.g. "OR1200_").

    Returns:
        List of chunk dicts, each:
        {
          _key, doc_path, doc_version, source_commit, valid_from_epoch,
          text, word_count, chunk_index, section_header, embedding (None)
        }
    """
    chunk_size  = chunk_size  or LOCAL_GRAPHRAG_CHUNK_SIZE
    overlap     = overlap     or LOCAL_GRAPHRAG_CHUNK_OVERLAP

    if not os.path.exists(doc_path):
        raise FileNotFoundError(f"Document not found: {doc_path}")

    print(f"[chunker] Processing: {os.path.basename(doc_path)}"
          f"  (version={doc_version}, epoch={valid_from_epoch})")

    raw_text = _convert_to_text(doc_path)
    words    = _split_into_words(raw_text)

    if not words:
        print(f"[chunker] WARNING: empty document — {doc_path}")
        return []

    raw_chunks = _chunk_words(words, chunk_size, overlap)
    doc_basename = os.path.basename(doc_path)

    result = []
    for idx, chunk_text in enumerate(raw_chunks):
        key = f"{prefix}{_sha_key(chunk_text, f':{idx}')}"
        result.append({
            "_key":             key,
            "doc_path":         doc_path,
            "doc_basename":     doc_basename,
            "doc_version":      doc_version,
            "source_commit":    source_commit,
            "valid_from_epoch": valid_from_epoch,
            "text":             chunk_text,
            "word_count":       len(chunk_text.split()),
            "chunk_index":      idx,
            "total_chunks":     len(raw_chunks),
            "section_header":   _detect_section_header(chunk_text),
            "embedding":        None,   # filled by extractor
        })

    print(f"[chunker] {len(result)} chunks from {doc_basename}")
    return result
