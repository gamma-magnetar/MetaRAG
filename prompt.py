"""L4 (prep) — assemble the prompt.

system  = condensed rulebook (from rules.yaml) + hard constraints.
user    = retrieved table cards + joins + rules + glossary + few-shot golden
          queries, then the question. The model is told to use ONLY the provided
          schema, which (with the guardrails) is what keeps it from inventing columns.
"""
from __future__ import annotations
from .retriever import Hit


def build_system_prompt(reg) -> str:
    lines = [
        "You are an expert Redshift/Metabase SQL analyst for the Cashfree Operations team.",
        "Write ONE correct, read-only Redshift SQL query that answers the user's question.",
        "",
        "Hard constraints:",
        "- Use ONLY tables and columns shown in the provided context. If something needed is "
        "missing, say so in a comment instead of inventing it.",
        "- Redshift dialect only (NVL, COALESCE, NULLIF, DATEDIFF, DATEADD, DATE_TRUNC, LISTAGG, "
        "ROW_NUMBER, GETDATE). SELECT-only — never DDL/DML.",
        "- Always date-bound cftransactions / cforders on addedon; if the user gave no range, "
        "use {{from_date}} / {{to_date}} and note it.",
        "- Prefer Metabase params ({{merchantId}}, {{orgid}}, {{from_date}}, {{to_date}}).",
        "- Start with a one-line comment stating the join logic, then the query.",
        "",
        "Key rules:",
    ]
    for r in reg.rules:
        lines.append(f"- {r['title']}: {r['text']}")
    return "\n".join(lines)


def _fmt_table(h: Hit) -> str:
    m = h.doc["meta"]
    cols = ", ".join(f"{c['name']} {c['type']}" for c in m.get("columns", []))
    s = f"### {m['schema']}.{m['table']}"
    if m.get("note"):
        s += f"\n{m['note']}"
    if m.get("key_columns"):
        s += f"\nkey columns: {', '.join(m['key_columns'])}"
    s += f"\ncolumns: {cols}"
    return s


def build_user_prompt(question: str, grouped: dict[str, list[Hit]]) -> str:
    parts: list[str] = []

    if grouped.get("table"):
        parts.append("## Relevant tables\n" + "\n\n".join(_fmt_table(h) for h in grouped["table"]))
    if grouped.get("join"):
        parts.append("## Joins\n" + "\n".join(
            f"- {h.doc['meta']['from']} -> {h.doc['meta']['to']}  ({h.doc['meta'].get('note','')})"
            for h in grouped["join"]))
    if grouped.get("glossary"):
        parts.append("## Definitions\n" + "\n".join(
            f"- {h.doc['meta']['term']}: {h.doc['meta']['definition']}" for h in grouped["glossary"]))
    if grouped.get("dictionary"):
        parts.append("## Reference\n" + "\n".join(h.doc["text"] for h in grouped["dictionary"]))
    if grouped.get("rule"):
        parts.append("## Applicable rules\n" + "\n".join(
            f"- {h.doc['meta']['title']}: {h.doc['meta']['text']}" for h in grouped["rule"]))
    if grouped.get("golden"):
        parts.append("## Worked examples (adapt, don't copy blindly)\n" + "\n\n".join(
            f"Q: {h.doc['meta']['question']}\n{h.doc['meta']['sql']}" for h in grouped["golden"]))

    parts.append(f"## Question\n{question}\n\nReturn only the SQL (with the leading join-logic comment).")
    return "\n\n".join(parts)
