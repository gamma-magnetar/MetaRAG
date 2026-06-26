"""L5 — static SQL guardrails (no DB needed).

Catches the failure modes that matter before a human ever runs the query:
  • not read-only (DDL/DML)           -> hard error
  • multiple statements                -> hard error
  • cftransactions/cforders unbounded  -> warning (the "timeout trap")
  • references a table not in registry -> warning (possible hallucination)

Optional live EXPLAIN against Redshift lives in redshift.py and is wired in by the
pipeline when credentials are present.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|copy|unload|call|vacuum)\b",
    re.I)
BIG_TABLES = ("cftransactions", "cforders")
_DATEISH = re.compile(r"(addedon|txtime|gmv_date|\{\{\s*from_date\s*\}\})", re.I)
_TABLE_REF = re.compile(r"\b(from|join)\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)", re.I)


@dataclass
class ValidationResult:
    sql: str
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    referenced_tables: list[str] = field(default_factory=list)


def validate_sql(sql: str, reg=None) -> ValidationResult:
    res = ValidationResult(sql=sql)
    body = re.sub(r"--.*?$|/\*.*?\*/", "", sql, flags=re.S | re.M)  # strip comments

    if FORBIDDEN.search(body):
        res.ok = False
        res.errors.append("Query is not read-only (found a write/DDL keyword). SELECT-only is required.")

    statements = [s for s in body.split(";") if s.strip()]
    if len(statements) > 1:
        res.ok = False
        res.errors.append("Multiple statements detected; return a single SELECT.")

    if not re.search(r"\bselect\b", body, re.I):
        res.warnings.append("No SELECT found — is this a valid query?")

    refs = [m.group(2).lower() for m in _TABLE_REF.finditer(body)]
    res.referenced_tables = sorted(set(refs))

    for bt in BIG_TABLES:
        if re.search(rf"\b{bt}\b", body, re.I) and not _DATEISH.search(body):
            res.warnings.append(
                f"`{bt}` is queried without an obvious date bound on addedon — this can crash "
                f"the cluster (the timeout trap). Add a date range.")

    if reg is not None:
        known = reg.table_names()
        for ref in res.referenced_tables:
            if ref not in known and ref.split(".")[-1] not in known:
                res.warnings.append(f"Table `{ref}` is not in the registry — verify it exists.")
    return res
