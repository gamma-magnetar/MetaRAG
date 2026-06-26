"""L0 -> docs — render the registry to a human-readable DATABOOK.md.

The DATABOOK is generated output, not the master. Edit the registry, run
`python rag.py render-databook`, and the doc regenerates — the same artifact you
upload to the Gem as a knowledge file.
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict


def render_databook(reg) -> str:
    out: list[str] = []
    w = out.append

    w("# Cashfree Ops — DATABOOK (generated)")
    w("\n*Generated from the registry. Do not edit by hand — edit `registry/` and re-render.*\n")
    w(f"- **Tables:** {len(reg.tables)}  ·  **Joins:** {len(reg.joins)}  ·  "
      f"**Rules:** {len(reg.rules)}  ·  **Golden queries:** {len(reg.golden_queries)}\n")

    # tables grouped by schema
    by_schema: dict[str, list[dict]] = defaultdict(list)
    for t in reg.tables:
        by_schema[t["schema"]].append(t)
    w("## Tables\n")
    for schema in sorted(by_schema):
        w(f"### Schema `{schema}`\n")
        for t in sorted(by_schema[schema], key=lambda x: x["table"]):
            w(f"#### `{schema}.{t['table']}`")
            if t.get("note"):
                w(t["note"])
            if t.get("key_columns"):
                w(f"\n*key columns:* {', '.join(t['key_columns'])}")
            cols = ", ".join(f"{c['name']} {c['type']}" for c in t.get("columns", []))
            w("\n```\n" + cols + "\n```\n")

    w("## Join map\n")
    for j in reg.joins:
        w(f"- `{j['from']}` → `{j['to']}`  — {j.get('note','')}")
    w("")

    w("## Rules\n")
    for r in reg.rules:
        w(f"- **{r['title']}** — {r['text']}")
    w("")

    w("## Glossary\n")
    for g in reg.glossary:
        w(f"- **{g['term']}** — {g['definition']}")
    w("")

    d = reg.dictionaries or {}
    if d.get("products"):
        w("## Product codes\n")
        for p in d["products"]:
            extra = f" — {p['note']}" if p.get("note") else ""
            w(f"- `{p['code']}` = {p['meaning']}{extra}")
        w("")

    w("## Golden queries\n")
    for q in reg.golden_queries:
        w(f"### {q['question']}")
        if q.get("note"):
            w(f"*{q['note']}*")
        w("\n```sql\n" + q["sql"].strip() + "\n```\n")

    return "\n".join(out)


def write_databook(reg, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_databook(reg))
    return path
