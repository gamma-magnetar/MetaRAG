"""L1 — the self-updating write path.

`add_table` is the automated version of the manual flow we ran for
merchant_gmv_master_data_base:
  1. get the real columns (live introspection from Redshift, or a provided list),
  2. build/replace the table card in the registry (the source of truth),
  3. (the CLI then re-renders the DATABOOK and rebuilds the index).

Human approval = you reviewing the printed diff and the git commit. Versioning =
git. This keeps writes governed instead of silently mutating the knowledge base.
"""
from __future__ import annotations

from .registry import load_registry, save_tables

KEYCOLS_PRIORITY = ["id", "merchantid", "mid", "orgid", "accountid", "beneid",
                    "cftxnid", "cforderid", "transactionid", "caseid", "ticketid",
                    "partnerid", "cmsprofileid"]


def _key_columns(columns: list[dict]) -> list[str]:
    names = {c["name"] for c in columns}
    return [k for k in KEYCOLS_PRIORITY if k in names][:4]


def add_table(settings, schema: str, table: str, note: str = "",
              columns: list[dict] | None = None) -> dict:
    """Add or replace a table card. `columns` = [{name,type}]; if omitted, introspect Redshift.

    Returns the new card. Raises if columns can't be obtained.
    """
    if columns is None:
        from .redshift import get_redshift
        rs = get_redshift(settings)
        if rs is None:
            raise RuntimeError(
                "No columns provided and Redshift is not configured.\n"
                "Either set REDSHIFT_* in .env, or pass --columns name:type,name:type ...")
        columns = rs.introspect_columns(schema, table)
        if not columns:
            raise RuntimeError(f"svv_columns returned nothing for {schema}.{table} — check the name.")

    card = {
        "schema": schema, "table": table,
        "key_columns": _key_columns(columns),
        "note": note,
        "columns": columns,
    }

    reg = load_registry(settings.registry_path)
    tables = list(reg.tables)
    existing = next((i for i, t in enumerate(tables)
                     if t["schema"] == schema and t["table"] == table), None)
    action = "replaced" if existing is not None else "added"
    if existing is not None:
        # preserve a hand-written note if the caller didn't supply one
        if not note and tables[existing].get("note"):
            card["note"] = tables[existing]["note"]
        tables[existing] = card
    else:
        tables.append(card)
    tables.sort(key=lambda t: (t["schema"], t["table"]))
    save_tables(settings.registry_path, tables)

    card["_action"] = action
    return card
