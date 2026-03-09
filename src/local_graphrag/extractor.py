"""
src/local_graphrag/extractor.py — Local LLM entity and relation extractor.

Extracts hardware IC entities and relationships from text chunks using either:
  - OpenAI API (gpt-4o or configurable model)
  - Ollama (local open-source LLMs, e.g. llama3.1:8b)

Output is compatible with the existing OR1200_Entities / OR1200_Relations schema
so the existing consolidator.py and bridger_bulk.py work unchanged.

Usage:
    from local_graphrag.extractor import EntityExtractor

    extractor = EntityExtractor(backend="ollama")
    entities, relations = extractor.extract_from_chunks(chunks, prefix="OR1200_")
"""

import json
import hashlib
import time
import os
import sys

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from config import GRAPHRAG_ENTITY_TYPES, OPENAI_API_KEY
from config_temporal import (
    LOCAL_GRAPHRAG_BACKEND, OLLAMA_BASE_URL, OLLAMA_MODEL,
    ARANGO_DATABASE,
)


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert hardware design knowledge extractor specialising in \
integrated circuit (IC) and processor architecture documentation. \
Extract entities and relationships from the provided text.

ENTITY TYPES (use exact type strings):
{entity_types}

OUTPUT FORMAT (valid JSON only, no markdown fences):
{{
  "entities": [
    {{"name": "string", "type": "ENTITY_TYPE", "description": "max 60 words", "aliases": ["alt_name"]}}
  ],
  "relations": [
    {{"source": "entity_name", "relation": "RELATION_TYPE", "target": "entity_name", "context": "brief"}}
  ]
}}

Rules:
- Only use entity types from the list above.
- Entity names must be concise (≤5 words).
- Relations must have both source and target matching an entity in this extraction.
- Output ONLY the JSON. No explanation, no markdown."""

USER_PROMPT = """Extract hardware design entities and relationships from this text:

<text>
{chunk_text}
</text>"""


def _build_messages(chunk_text: str) -> list[dict]:
    entity_types_str = "\n".join(f"  - {t}" for t in GRAPHRAG_ENTITY_TYPES)
    system = SYSTEM_PROMPT.format(entity_types=entity_types_str)
    user = USER_PROMPT.format(chunk_text=chunk_text[:4000])  # hard cap to stay in context
    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]


def _parse_llm_response(raw: str, chunk_key: str) -> tuple[list[dict], list[dict]]:
    """Parse LLM JSON output into (entities, relations) lists."""
    try:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:])
            if text.endswith("```"):
                text = text[:-3]
        data = json.loads(text.strip())
    except json.JSONDecodeError as e:
        print(f"    [extractor] WARNING: JSON parse error in chunk {chunk_key}: {e}")
        return [], []

    entities  = data.get("entities", [])
    relations = data.get("relations", [])

    if not isinstance(entities, list):
        entities = []
    if not isinstance(relations, list):
        relations = []

    return entities, relations


# ---------------------------------------------------------------------------
# Backend-specific callers
# ---------------------------------------------------------------------------

def _call_openai(messages: list[dict], model: str = "gpt-4o") -> str:
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        print(f"    [extractor] OpenAI error: {e}")
        return ""


def _call_ollama(messages: list[dict], model: str = None,
                 base_url: str = None) -> str:
    model    = model    or OLLAMA_MODEL
    base_url = base_url or OLLAMA_BASE_URL
    try:
        import requests
        resp = requests.post(
            f"{base_url}/api/chat",
            json={
                "model":    model,
                "messages": messages,
                "stream":   False,
                "options":  {"temperature": 0.0},
                "format":   "json",
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
    except Exception as e:
        print(f"    [extractor] Ollama error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Main extractor class
# ---------------------------------------------------------------------------

class EntityExtractor:
    def __init__(
        self,
        backend: str = None,
        model: str = None,
        retry_attempts: int = 2,
        retry_delay: float = 2.0,
    ):
        self.backend = backend or LOCAL_GRAPHRAG_BACKEND
        self.model   = model
        self.retry_attempts = retry_attempts
        self.retry_delay    = retry_delay

        print(f"[extractor] Backend: {self.backend}"
              f"{'  model: ' + (self.model or 'default') if self.model else ''}")

    def _call_llm(self, messages: list[dict]) -> str:
        for attempt in range(self.retry_attempts + 1):
            if self.backend == "openai":
                raw = _call_openai(messages, model=self.model or "gpt-4o")
            elif self.backend == "ollama":
                raw = _call_ollama(messages, model=self.model)
            else:
                raise ValueError(f"Unknown backend: {self.backend!r}. Use 'openai' or 'ollama'.")

            if raw:
                return raw
            if attempt < self.retry_attempts:
                time.sleep(self.retry_delay)
        return ""

    def extract_from_chunk(
        self, chunk: dict, prefix: str = ""
    ) -> tuple[list[dict], list[dict]]:
        """Extract entities and relations from a single chunk dict."""
        chunk_key  = chunk.get("_key", "unknown")
        chunk_text = chunk.get("text", "")

        messages = _build_messages(chunk_text)
        raw = self._call_llm(messages)
        raw_entities, raw_relations = _parse_llm_response(raw, chunk_key)

        # Enrich with provenance metadata and generate ArangoDB-compatible _key
        entities = []
        entity_key_map = {}  # name → _key for relation wiring

        for ent in raw_entities:
            name = ent.get("name", "").strip()
            if not name:
                continue
            ent_key = f"{prefix}{hashlib.md5(name.lower().encode()).hexdigest()[:12]}"
            entity_key_map[name.lower()] = ent_key
            entities.append({
                "_key":        ent_key,
                "name":        name,
                "type":        ent.get("type", "ARCHITECTURE_FEATURE"),
                "description": ent.get("description", "")[:300],
                "aliases":     ent.get("aliases", []),
                "source_chunk": chunk_key,
                "doc_version":  chunk.get("doc_version"),
                "valid_from_epoch": chunk.get("valid_from_epoch"),
                "embedding":    None,  # filled by embedding step
            })

        relations = []
        for rel in raw_relations:
            src_name = rel.get("source", "").strip().lower()
            tgt_name = rel.get("target", "").strip().lower()
            src_key  = entity_key_map.get(src_name)
            tgt_key  = entity_key_map.get(tgt_name)
            if not src_key or not tgt_key:
                continue  # skip dangling relations

            rel_key = hashlib.md5(
                f"{src_key}:{rel.get('relation','REL')}:{tgt_key}:{chunk_key}".encode()
            ).hexdigest()[:16]

            relations.append({
                "_key":    rel_key,
                "_from":   f"{prefix}Entities/{src_key}",
                "_to":     f"{prefix}Entities/{tgt_key}",
                "type":    rel.get("relation", "RELATED_TO"),
                "context": rel.get("context", "")[:200],
                "source_chunk": chunk_key,
            })

        return entities, relations

    def extract_from_chunks(
        self,
        chunks: list[dict],
        prefix: str = "",
        progress_every: int = 10,
    ) -> tuple[list[dict], list[dict]]:
        """
        Extract entities and relations from a list of chunks.
        Returns (all_entities, all_relations) deduplicated by _key.
        """
        all_entities: dict[str, dict] = {}
        all_relations: dict[str, dict] = {}
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            if i % progress_every == 0:
                print(f"  [extractor] chunk {i+1}/{total} …")

            ents, rels = self.extract_from_chunk(chunk, prefix=prefix)

            for e in ents:
                # Merge: keep first occurrence but accumulate aliases
                if e["_key"] in all_entities:
                    existing = all_entities[e["_key"]]
                    existing["aliases"] = list(set(
                        existing.get("aliases", []) + e.get("aliases", [])
                    ))
                else:
                    all_entities[e["_key"]] = e

            for r in rels:
                all_relations[r["_key"]] = r

        print(f"[extractor] Done — {len(all_entities)} entities, "
              f"{len(all_relations)} relations extracted from {total} chunks.")

        return list(all_entities.values()), list(all_relations.values())
