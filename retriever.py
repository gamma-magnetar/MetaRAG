"""L3 — retrieval: hybrid (dense + BM25) fused with reciprocal-rank fusion (RRF).

Hybrid matters for text-to-SQL because table/column names are literal tokens
(`cftxnid`, `merchant_gmv_master_data_base`) that BM25 nails and pure embeddings
can miss. RRF avoids calibrating the two score scales against each other.

`search_context` is type-aware: it pulls a balanced budget of each document type
(tables, joins, rules, glossary, golden queries) so a multi-table question still
gets enough schema cards instead of being crowded out by rules/examples.
"""
from __future__ import annotations
from dataclasses import dataclass

from .store import IndexStore
from .embeddings import Embedder

# how many of each document type to include in the assembled context
PER_TYPE_CAP = {"table": 6, "join": 5, "rule": 4, "glossary": 3, "golden": 3, "dictionary": 2}


@dataclass
class Hit:
    doc: dict
    score: float


class HybridRetriever:
    def __init__(self, store: IndexStore, embedder: Embedder, settings):
        self.store = store
        self.embedder = embedder
        self.s = settings

    def _fuse(self, query: str, pool: int) -> list[tuple[int, float]]:
        rrf_k = self.s.rrf_k
        ranks: dict[int, float] = {}
        for rank, (i, _) in enumerate(self.store.bm25_search(query, pool)):
            ranks[i] = ranks.get(i, 0.0) + 1.0 / (rrf_k + rank)
        try:
            qv = self.embedder.embed_query(query)
            for rank, (i, _) in enumerate(self.store.dense_search(qv, pool)):
                ranks[i] = ranks.get(i, 0.0) + 1.0 / (rrf_k + rank)
        except Exception as e:
            print(f"[retriever] dense search skipped ({e}); using BM25 only.")
        return sorted(ranks.items(), key=lambda kv: -kv[1])

    def search(self, query: str, k: int | None = None) -> list[Hit]:
        k = k or self.s.top_k
        return [Hit(self.store.docs[i], s) for i, s in self._fuse(query, self.s.candidate_k)[:k]]

    def search_context(self, query: str) -> dict[str, list[Hit]]:
        """Balanced, type-capped context for prompt assembly / generation."""
        grouped: dict[str, list[Hit]] = {}
        for i, score in self._fuse(query, self.s.candidate_k):
            d = self.store.docs[i]
            bucket = grouped.setdefault(d["type"], [])
            if len(bucket) < PER_TYPE_CAP.get(d["type"], 3):
                bucket.append(Hit(doc=d, score=score))
        return grouped
