"""Sentence-embedding wrapper for memory retrieval.

Tries BAAI/bge-small-en-v1.5 via sentence-transformers. Downloading the
model weights requires internet access to huggingface.co on first run —
if that's unavailable (offline dev, a restricted network), or the model
just hasn't been cached yet, this falls back to a deterministic hashed
bag-of-words embedding so the rest of the memory pipeline (storage,
retrieval, reranking) is fully exercisable end-to-end, just without real
semantic similarity. Pre-download the real model once with internet
access via:

    python3 -c "from sentence_transformers import SentenceTransformer; \
                 SentenceTransformer('BAAI/bge-small-en-v1.5')"

and it's cached locally for every run after that, real or offline.
"""
from __future__ import annotations

import hashlib
import logging
import re

import numpy as np

logger = logging.getLogger("llm_core.memory.embeddings")

_FALLBACK_DIM = 384   # matches bge-small-en-v1.5's real output dimension,
                       # so fallback vectors are drop-in compatible with a
                       # ChromaDB collection created while the real model
                       # was active (and vice versa isn't silently corrupt).


class EmbeddingModel:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model = None
        self.backend = "hash-fallback"
        self.dim = _FALLBACK_DIM

        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
            self.backend = "sentence-transformers"
            self.dim = self._model.get_sentence_embedding_dimension()
            logger.info("loaded real embedding model %s (dim=%d)", model_name, self.dim)
        except Exception as exc:
            logger.warning(
                "could not load %s (%s); using hash-fallback embeddings — "
                "semantic search quality will be poor until the real model "
                "is downloaded (see module docstring)", model_name, exc,
            )

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._model is not None:
            return np.asarray(self._model.encode(texts, normalize_embeddings=True), dtype=np.float32)
        return np.stack([self._hash_embed(t) for t in texts]).astype(np.float32)

    def _hash_embed(self, text: str) -> np.ndarray:
        """Deterministic bag-of-hashed-tokens vector, L2-normalized. Not
        semantically meaningful (no notion of synonyms/similarity beyond
        exact token overlap), but stable, fast, and dependency-free — good
        enough to prove the storage/retrieval plumbing works."""
        vec = np.zeros(_FALLBACK_DIM, dtype=np.float32)
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for tok in tokens:
            idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % _FALLBACK_DIM
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
