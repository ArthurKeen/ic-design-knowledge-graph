"""
src/local_graphrag/embedder.py — Embedding generation for local GraphRAG entities.

Generates float-list embeddings for each entity extracted by extractor.py.
Writes the result into the entity dict's ``embedding`` field in-place.

Backends:
    sentence_transformers  — local, free, no API key  (default)
    openai                 — OpenAI text-embedding-3-small (requires OPENAI_API_KEY)

Usage:
    from local_graphrag.embedder import embed_entities

    entities = embed_entities(entities, backend="sentence_transformers")
"""

import os
import sys
from typing import Literal

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from config import OPENAI_API_KEY

# Default ST model — 384-dim, very fast on CPU
_DEFAULT_ST_MODEL = os.getenv("EMBEDDER_ST_MODEL", "all-MiniLM-L6-v2")
# OpenAI model — 1536-dim
_DEFAULT_OAI_MODEL = os.getenv("EMBEDDER_OAI_MODEL", "text-embedding-3-small")

_EMBEDDER_BATCH_SIZE = int(os.getenv("EMBEDDER_BATCH_SIZE", "256"))
_MAX_TEXT_LENGTH = int(os.getenv("EMBEDDER_MAX_TEXT_LENGTH", "512"))


def _embed_sentence_transformers(
    texts: list[str], model_name: str = _DEFAULT_ST_MODEL
) -> list[list[float]]:
    """Batch-encode texts using SentenceTransformers."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "SentenceTransformer not installed. Run: pip install sentence-transformers"
        )
    model = SentenceTransformer(model_name)
    vecs = model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def _embed_openai(texts: list[str], model: str = _DEFAULT_OAI_MODEL) -> list[list[float]]:
    """Batch-encode texts using the OpenAI embedding API."""
    try:
        import openai
    except ImportError:
        raise ImportError("openai not installed. Run: pip install openai")

    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    # OpenAI supports up to 2048 inputs per call; chunk to be safe
    results: list[list[float]] = []
    batch_size = _EMBEDDER_BATCH_SIZE
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(input=batch, model=model)
        results.extend([item.embedding for item in response.data])
    return results


def embed_entities(
    entities: list[dict],
    backend: Literal["sentence_transformers", "openai"] = "sentence_transformers",
    model: str = None,
    text_field: str = "description",
    progress_every: int = 50,
) -> list[dict]:
    """
    Generate embeddings for a list of entity dicts and store them in ``entity['embedding']``.

    The text used for embedding is formed by concatenating the entity ``name``
    and its ``description`` (or whichever field is given by ``text_field``).
    Entities that already have a non-None embedding are skipped.

    Args:
        entities:       List of entity dicts from extractor.extract_from_chunks()
        backend:        "sentence_transformers" (local, free) or "openai"
        model:          Override model name (else uses backend default)
        text_field:     Entity field to embed alongside the name
        progress_every: Print progress every N entities

    Returns:
        The same list, with ``embedding`` fields populated in-place.
    """
    if not entities:
        return entities

    # Separate entities that still need embeddings
    needs_embed = [e for e in entities if not e.get("embedding")]
    if not needs_embed:
        print(f"[embedder] All {len(entities)} entities already have embeddings — skipping.")
        return entities

    print(f"[embedder] Generating embeddings for {len(needs_embed)} entities "
          f"via '{backend}' …")

    # Build text strings: "{name}: {description}"
    texts = []
    for e in needs_embed:
        name = e.get("name", "")
        detail = e.get(text_field, "") or ""
        texts.append(f"{name}: {detail}"[:_MAX_TEXT_LENGTH])

    # Call selected backend
    if backend == "sentence_transformers":
        vectors = _embed_sentence_transformers(texts, model or _DEFAULT_ST_MODEL)
    elif backend == "openai":
        vectors = _embed_openai(texts, model or _DEFAULT_OAI_MODEL)
    else:
        raise ValueError(f"Unknown embedding backend: {backend!r}. Use 'sentence_transformers' or 'openai'.")

    # Write back
    for entity, vec in zip(needs_embed, vectors):
        entity["embedding"] = vec

    print(f"[embedder] Done — {len(needs_embed)} embeddings generated "
          f"(dim={len(vectors[0]) if vectors else 'N/A'}).")
    return entities
