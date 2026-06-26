"""Cashfree Ops RAG — a retrieval-grounded text-to-SQL assistant for the ops team.

Package layout (each module maps to a layer from the design deck):

    config.py      settings (config.yaml + .env)
    registry.py    L0  source of truth — load/save the structured registry
    corpus.py      L2  registry -> retrieval documents (chunking)
    embeddings.py  L2  Embedder: Gemini (default) or offline hashing fallback
    store.py       L2  local dense + BM25 index (persist/load)
    retriever.py   L3  hybrid search (dense + BM25) + reciprocal-rank fusion
    prompt.py      L4  assemble system + retrieved context + few-shot examples
    llm.py         L4  LLM: Gemini text-to-SQL generation
    guardrails.py  L5  validate SQL (read-only, date-bound, known tables)
    redshift.py    L1/L5  optional live Redshift (introspection + EXPLAIN)
    ingest.py      L1  self-updating: add/replace a table in the registry
    databook.py    L0->docs  render the registry to a Markdown DATABOOK
    pipeline.py    L3-L5  the "ask" flow: retrieve -> generate -> validate
    cli.py         entrypoint commands
"""
__version__ = "0.1.0"
