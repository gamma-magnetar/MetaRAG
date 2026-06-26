"""L2 (prep) — turn the registry into retrieval documents.

One document per table card, join edge, rule, glossary term, golden query, and
dictionary block. Each document carries a `text` field (what gets embedded /
BM25-indexed) and `meta` (type, table, etc.) used to assemble context later.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class Document:
    id: str
    type: str                 # table | join | rule | glossary | golden | dictionary
    title: str
    text: str
    meta: dict = field(default_factory=dict)


# ---- tokenizer (shared by BM25) --------------------------------------------
_word = re.compile(r"[a-z0-9_]+")

def tokenize(text: str) -> list[str]:
    """Lowercase tokens; also split snake_case so 'merchant_gmv' matches 'gmv'."""
    toks: list[str] = []
    for t in _word.findall(text.lower()):
        toks.append(t)
        if "_" in t:
            toks.extend(p for p in t.split("_") if p)
    return toks


def _table_text(t: dict) -> str:
    cols = ", ".join(f"{c['name']} {c['type']}" for c in t.get("columns", []))
    keys = ", ".join(t.get("key_columns", []))
    parts = [f"{t['schema']}.{t['table']}"]
    if t.get("note"):
        parts.append(t["note"])
    if keys:
        parts.append(f"key columns: {keys}")
    parts.append(f"columns: {cols}")
    return "\n".join(parts)


def build_documents(reg) -> list[Document]:
    docs: list[Document] = []

    for t in reg.tables:
        full = f"{t['schema']}.{t['table']}"
        docs.append(Document(
            id=f"table:{full}", type="table", title=full,
            text=_table_text(t),
            meta={"schema": t["schema"], "table": t["table"],
                  "key_columns": t.get("key_columns", []), "note": t.get("note", ""),
                  "columns": t.get("columns", [])},
        ))

    for j in reg.joins:
        text = f"JOIN {j['from']} -> {j['to']}. {j.get('note','')}"
        docs.append(Document(id=f"join:{j['from']}->{j['to']}", type="join",
                             title=f"{j['from']} -> {j['to']}", text=text, meta=j))

    for r in reg.rules:
        docs.append(Document(id=f"rule:{r['id']}", type="rule", title=r["title"],
                             text=f"RULE — {r['title']}: {r['text']}", meta=r))

    for g in reg.glossary:
        tbls = ", ".join(g.get("tables", []))
        docs.append(Document(id=f"glossary:{g['term']}", type="glossary", title=g["term"],
                             text=f"DEFINITION — {g['term']}: {g['definition']} (tables: {tbls})", meta=g))

    for i, q in enumerate(reg.golden_queries):
        tbls = ", ".join(q.get("tables", []))
        text = f"EXAMPLE QUESTION: {q['question']}\nTables: {tbls}\nSQL:\n{q['sql']}"
        docs.append(Document(id=f"golden:{i}", type="golden", title=q["question"], text=text, meta=q))

    # dictionaries -> a few searchable blocks
    d = reg.dictionaries or {}
    if d.get("products"):
        text = "PRODUCT CODES: " + "; ".join(
            f"{p['code']} = {p['meaning']}" + (f" ({p['note']})" if p.get("note") else "")
            for p in d["products"])
        docs.append(Document(id="dict:products", type="dictionary", title="Product codes", text=text, meta={}))
    if d.get("status_codes"):
        text = "STATUS CODES: " + "; ".join(f"{k}={v}" for k, v in d["status_codes"].items())
        docs.append(Document(id="dict:status", type="dictionary", title="Status codes", text=text, meta={}))
    for grp in (d.get("reg_key_groups") or []):
        text = f"REG KEYS ({grp['group']}): " + ", ".join(grp["keys"])
        docs.append(Document(id=f"dict:regkeys:{grp['group']}", type="dictionary",
                             title=f"Reg keys — {grp['group']}", text=text, meta={}))
    return docs
