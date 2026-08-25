"""Cross-encoder reranker for improving memory retrieval quality: given a
query and a set of candidate documents (already narrowed down by the
vector store's approximate similarity search), re-scores each candidate
against the query directly for a more accurate final ranking.

Tries BAAI/bge-reranker-base via sentence-transformers' CrossEncoder.
Falls back to a simple lexical-overlap scorer under the same conditions as
memory/embeddings.py (no internet/HF access, model not cached) — same
reasoning, same tradeoff: the retrieval pipeline stays fully testable, at
the cost of ranking quality until the real model is available.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("llm_core.memory.reranker")


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self.model_name = model_name
        self._model = None
        self.backend = "lexical-fallback"

        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(model_name)
            self.backend = "cross-encoder"
            logger.info("loaded real reranker model %s", model_name)
        except Exception as exc:
            logger.warning(
                "could not load %s (%s); using lexical-overlap fallback — "
                "reranking quality will be poor until the real model is "
                "downloaded", model_name, exc,
            )

    def rerank(self, query: str, documents: list[str], top_k: int = 3) -> list[tuple[int, float]]:
        """Returns (original_index, score) pairs for the top_k documents,
        sorted best-first."""
        if not documents:
            return []

        if self._model is not None:
            pairs = [(query, doc) for doc in documents]
            scores = self._model.predict(pairs)
        else:
            scores = [self._lexical_overlap(query, doc) for doc in documents]

        ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _lexical_overlap(query: str, doc: str) -> float:
        q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        d_tokens = set(re.findall(r"[a-z0-9]+", doc.lower()))
        if not q_tokens or not d_tokens:
            return 0.0
        return len(q_tokens & d_tokens) / len(q_tokens | d_tokens)   # Jaccard similarity
