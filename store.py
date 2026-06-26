"""L2 — the index store.

A dependency-light local store: document texts + a dense embedding matrix (numpy)
persisted to data/index/. BM25 is rebuilt in memory on load (cheap). No external
vector database needed for the base; swap this module for pgvector/Qdrant later
without touching the retriever's interface.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from rank_bm25 import BM25Okapi

from .corpus import Document, tokenize


class IndexStore:
    def __init__(self):
        self.docs: list[dict] = []
        self.embeddings: np.ndarray | None = None
        self.embedder_label: str = ""
        self._bm25: BM25Okapi | None = None

    # ---- build / persist ----
    def build(self, docs: list[Document], embedder, label: str):
        self.docs = [d.__dict__ for d in docs]
        self.embeddings = embedder.embed_documents([d.text for d in docs])
        self.embedder_label = label
        self._fit_bm25()

    def save(self, index_dir: Path):
        index_dir = Path(index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)
        (index_dir / "chunks.json").write_text(json.dumps(self.docs, ensure_ascii=False))
        np.save(index_dir / "embeddings.npy", self.embeddings)
        (index_dir / "meta.json").write_text(json.dumps(
            {"embedder": self.embedder_label, "count": len(self.docs),
             "dim": int(self.embeddings.shape[1])}))

    @classmethod
    def load(cls, index_dir: Path) -> "IndexStore":
        index_dir = Path(index_dir)
        chunks = index_dir / "chunks.json"
        if not chunks.exists():
            raise FileNotFoundError(
                f"No index at {index_dir}. Build it first:  python rag.py index")
        s = cls()
        s.docs = json.loads(chunks.read_text())
        s.embeddings = np.load(index_dir / "embeddings.npy")
        meta = json.loads((index_dir / "meta.json").read_text())
        s.embedder_label = meta.get("embedder", "")
        s._fit_bm25()
        return s

    # ---- search ----
    def _fit_bm25(self):
        self._bm25 = BM25Okapi([tokenize(d["text"]) for d in self.docs])

    def dense_search(self, qvec: np.ndarray, k: int) -> list[tuple[int, float]]:
        sims = self.embeddings @ qvec
        idx = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in idx]

    def bm25_search(self, query: str, k: int) -> list[tuple[int, float]]:
        scores = self._bm25.get_scores(tokenize(query))
        idx = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in idx]
