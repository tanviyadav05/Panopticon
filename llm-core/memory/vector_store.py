"""Vector memory backed by ChromaDB's local persistent client — no
separate Chroma server process needed, it's an embedded library (SQLite +
a vector index under the hood), which fits this repo's "one process per
laptop, no extra infra to babysit" style.

Uses embeddings.EmbeddingModel directly (real model if available, hashed
fallback otherwise — see that module's docstring) rather than Chroma's
own default embedding function, so the same embedding backend is used
consistently everywhere in llm-core, not just here.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

logger = logging.getLogger("llm_core.memory.vector_store")


class VectorMemory:
    def __init__(self, persist_dir: str, collection_name: str = "panopticon_memory", embedding_model=None):
        import chromadb

        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(collection_name)

        if embedding_model is None:
            from memory.embeddings import EmbeddingModel
            embedding_model = EmbeddingModel()
        self._embedder = embedding_model

    def add(self, text: str, metadata: Optional[dict] = None, doc_id: Optional[str] = None) -> str:
        doc_id = doc_id or str(uuid.uuid4())
        vector = self._embedder.embed([text])[0]
        meta = dict(metadata or {})
        meta.setdefault("added_at", time.time())
        meta.setdefault("embedding_backend", self._embedder.backend)
        self._collection.add(
            ids=[doc_id], documents=[text],
            embeddings=[vector.tolist()], metadatas=[meta],
        )
        return doc_id

    def query(self, text: str, top_k: int = 8) -> list[dict]:
        if self._collection.count() == 0:
            return []
        vector = self._embedder.embed([text])[0]
        n = min(top_k, self._collection.count())
        result = self._collection.query(query_embeddings=[vector.tolist()], n_results=n)

        out = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for doc_id, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append({"id": doc_id, "text": doc, "metadata": meta, "distance": dist})
        return out

    def count(self) -> int:
        return self._collection.count()

    def delete(self, doc_id: str):
        self._collection.delete(ids=[doc_id])
