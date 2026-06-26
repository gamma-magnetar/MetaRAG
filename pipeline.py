"""L3-L5 — the answer pipeline: retrieve context, generate SQL, validate it.

Returns a structured Answer so the CLI (or a future API / Slack bot) can render it.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .retriever import HybridRetriever
from .prompt import build_system_prompt, build_user_prompt
from .llm import LLM
from .guardrails import validate_sql, ValidationResult


@dataclass
class Answer:
    question: str
    sql: str = ""
    context_tables: list[str] = field(default_factory=list)
    validation: ValidationResult | None = None
    explain: str | None = None


def answer_question(question: str, reg, retriever: HybridRetriever, llm: LLM,
                    redshift=None) -> Answer:
    grouped = retriever.search_context(question)
    ctx_tables = [h.doc["title"] for h in grouped.get("table", [])]

    system = build_system_prompt(reg)
    user = build_user_prompt(question, grouped)

    sql = llm.generate(system, user)  # raises (NullLLM) if no key — caught by caller
    val = validate_sql(sql, reg)

    explain_msg = None
    if redshift is not None and val.ok:
        ok, msg = redshift.explain(sql)
        explain_msg = msg
        if not ok:
            val.warnings.append(msg)

    return Answer(question=question, sql=sql, context_tables=ctx_tables,
                  validation=val, explain=explain_msg)
