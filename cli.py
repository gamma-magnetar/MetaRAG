"""CLI — the commands you'll actually run.

  index            build the search index from the registry
  search "Q"       show what retrieval returns (no LLM; great for debugging)
  ask "Q"          retrieve + generate SQL + validate  (needs GEMINI_API_KEY)
  chat             interactive ask loop
  add-table ...    self-updating ingest (introspect Redshift or pass --columns)
  render-databook  regenerate outputs/DATABOOK.md from the registry
  eval             retrieval regression over the golden queries
"""
from __future__ import annotations
import argparse
import sys

from .config import load_settings
from .registry import load_registry
from .corpus import build_documents
from .store import IndexStore
from .embeddings import get_embedder
from .retriever import HybridRetriever
from .llm import get_llm
from .pipeline import answer_question
from .databook import write_databook
from .ingest import add_table

# optional pretty printing
try:
    from rich import print as rprint
    from rich.panel import Panel
    from rich.syntax import Syntax
    _RICH = True
except Exception:
    _RICH = False
    def rprint(*a, **k): print(*a, **k)


def _rule(msg): print("\n" + "=" * 4 + f" {msg} " + "=" * (72 - len(msg)))


# ---------------- commands ----------------
def cmd_index(settings, args):
    reg = load_registry(settings.registry_path)
    docs = build_documents(reg)
    embedder, label = get_embedder(settings)
    print(f"Embedding {len(docs)} documents with: {label}")
    store = IndexStore()
    store.build(docs, embedder, label)
    store.save(settings.index_path)
    print(f"Index built ({len(docs)} docs, embedder={label}) -> {settings.index_path}")
    if label == "hashing":
        print("Note: no GEMINI_API_KEY, so dense embeddings are the offline fallback. "
              "Keyword (BM25) retrieval still works well for schema lookups.")


def _load_retriever(settings) -> HybridRetriever:
    store = IndexStore.load(settings.index_path)
    embedder, _ = get_embedder(settings)
    return HybridRetriever(store, embedder, settings)


def cmd_search(settings, args):
    retriever = _load_retriever(settings)
    hits = retriever.search(args.question, k=args.k)
    _rule(f"Top {len(hits)} results for: {args.question}")
    for h in hits:
        print(f"\n[{h.doc['type']}] {h.doc['title']}   (score {h.score:.4f})")
        snippet = h.doc["text"].strip().replace("\n", " ")
        print("   " + (snippet[:240] + ("…" if len(snippet) > 240 else "")))


def cmd_ask(settings, args):
    reg = load_registry(settings.registry_path)
    retriever = _load_retriever(settings)
    llm = get_llm(settings)
    redshift = None
    if args.explain:
        from .redshift import get_redshift
        redshift = get_redshift(settings)
    try:
        ans = answer_question(args.question, reg, retriever, llm, redshift)
    except RuntimeError as e:
        print(str(e)); return

    _rule("Generated SQL")
    if _RICH:
        rprint(Syntax(ans.sql, "sql", theme="ansi_dark", word_wrap=True))
    else:
        print(ans.sql)

    v = ans.validation
    if v:
        print()
        if v.errors:
            print("ERRORS:");  [print("  ✗ " + e) for e in v.errors]
        if v.warnings:
            print("WARNINGS:"); [print("  ! " + w) for w in v.warnings]
        if v.ok and not v.warnings:
            print("✓ passed read-only / date-bound checks")
    if ans.explain:
        print(f"\nEXPLAIN: {ans.explain}")
    print(f"\nContext tables used: {', '.join(ans.context_tables) or '(none)'}")


def cmd_chat(settings, args):
    reg = load_registry(settings.registry_path)
    retriever = _load_retriever(settings)
    llm = get_llm(settings)
    print("Ops SQL chat — type a question, or 'exit'.")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if q.lower() in {"exit", "quit", ""}:
            break
        try:
            ans = answer_question(q, reg, retriever, llm)
        except RuntimeError as e:
            print(str(e)); continue
        print("\n" + ans.sql)
        if ans.validation and ans.validation.warnings:
            [print("  ! " + w) for w in ans.validation.warnings]


def cmd_add_table(settings, args):
    columns = None
    if args.columns:
        columns = []
        for pair in args.columns.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            name, _, typ = pair.partition(":")
            columns.append({"name": name.strip(), "type": (typ.strip() or "character varying")})
    card = add_table(settings, args.schema, args.table, note=args.note or "", columns=columns)
    _rule(f"Table {card['_action']}: {card['schema']}.{card['table']}")
    print(f"key columns: {', '.join(card['key_columns']) or '(none)'}")
    print(f"columns ({len(card['columns'])}): " +
          ", ".join(f"{c['name']} {c['type']}" for c in card["columns"]))
    print("\nNext: review `git diff registry/tables.yaml`, then run:")
    print("  python rag.py render-databook && python rag.py index")


def cmd_render_databook(settings, args):
    reg = load_registry(settings.registry_path)
    path = write_databook(reg, settings.databook_file)
    print(f"DATABOOK written -> {path}")


def cmd_eval(settings, args):
    """Retrieval regression: does each golden query's expected table get retrieved?"""
    reg = load_registry(settings.registry_path)
    retriever = _load_retriever(settings)
    passed = 0
    _rule("Retrieval eval over golden queries")
    for q in reg.golden_queries:
        grouped = retriever.search_context(q["question"])
        got = {h.doc["meta"]["table"] for h in grouped.get("table", [])}
        want = set(q.get("tables", []))
        ok = want.issubset(got) if want else True
        passed += ok
        print(f"  {'✓' if ok else '✗'} {q['question'][:60]}")
        if not ok:
            print(f"      wanted {sorted(want)}  got tables {sorted(got)}")
    print(f"\n{passed}/{len(reg.golden_queries)} golden queries retrieved their expected tables")


# ---------------- arg parsing ----------------
def main(argv=None):
    p = argparse.ArgumentParser(prog="rag", description="Cashfree Ops RAG (text-to-SQL)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("index", help="build the search index from the registry")

    sp = sub.add_parser("search", help="retrieval only (debug)")
    sp.add_argument("question"); sp.add_argument("-k", type=int, default=8)

    sp = sub.add_parser("ask", help="retrieve + generate SQL + validate")
    sp.add_argument("question")
    sp.add_argument("--explain", action="store_true", help="also EXPLAIN against Redshift if configured")

    sub.add_parser("chat", help="interactive ask loop")

    sp = sub.add_parser("add-table", help="add/replace a table in the registry")
    sp.add_argument("schema"); sp.add_argument("table")
    sp.add_argument("--note", default="")
    sp.add_argument("--columns", default="",
                    help="name:type; name:type ... (semicolon-separated; omit to introspect Redshift)")

    sub.add_parser("render-databook", help="regenerate outputs/DATABOOK.md")
    sub.add_parser("eval", help="retrieval regression over golden queries")

    args = p.parse_args(argv)
    settings = load_settings()
    {
        "index": cmd_index, "search": cmd_search, "ask": cmd_ask, "chat": cmd_chat,
        "add-table": cmd_add_table, "render-databook": cmd_render_databook, "eval": cmd_eval,
    }[args.cmd](settings, args)


if __name__ == "__main__":
    main()
