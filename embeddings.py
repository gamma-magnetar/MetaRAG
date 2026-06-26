"""L2 — embeddings.

Two implementations behind one interface:
  • GeminiEmbedder  — recommended; uses gemini-embedding-001 with retrieval task types.
  • HashingEmbedder — offline, deterministic fallback (no API key, no torch). Not
    semantically strong, but lets the whole pipeline run end-to-end; BM25 carries the
    exact-token matching (table/column names) in the meantime.

get_embedder() picks Gemini when a key is present, otherwise the fallback.
"""
from __future__ import annotations
import hashlib
import numpy as np


class Embedder:
    dim: int
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def _l2(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.clip(n, 1e-9, None)


class HashingEmbedder(Embedder):
    """Hashes character 3-grams + word tokens into a fixed-dim, L2-normalised vector."""
    def __init__(self, dim: int = 512):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        t = text.lower()
        toks = t.split()
        grams = [t[i:i + 3] for i in range(max(0, len(t) - 2))]
        for feat in toks + grams:
            h = int(hashlib.md5(feat.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        return v

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return _l2(np.vstack([self._vec(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return _l2(self._vec(text)[None, :])[0]


class GeminiEmbedder(Embedder):
    def __init__(self, api_key: str, model: str = "gemini-embedding-001"):
        from google import genai  # lazy import so offline mode needs no package
        self._genai = genai
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.dim = 0  # set after first call

    def _embed(self, texts: list[str], task: str) -> np.ndarray:
        from google.genai import types
        out: list[list[float]] = []
        for i in range(0, len(texts), 100):  # batch
            batch = texts[i:i + 100]
            resp = self.client.models.embed_content(
                model=self.model, contents=batch,
                config=types.EmbedContentConfig(task_type=task),
            )
            out.extend(e.values for e in resp.embeddings)
        m = _l2(np.array(out, dtype=np.float32))
        self.dim = m.shape[1]
        return m

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


def get_embedder(settings) -> tuple[Embedder, str]:
    """Returns (embedder, label). Falls back to hashing when no Gemini key is set."""
    if settings.has_gemini:
        try:
            return GeminiEmbedder(settings.gemini_api_key, settings.embedding_model), "gemini"
        except Exception as e:  # missing package / bad key -> fall back
            print(f"[embeddings] Gemini unavailable ({e}); falling back to offline hashing.")
    return HashingEmbedder(settings.dense_dim_fallback), "hashing"
