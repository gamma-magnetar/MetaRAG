"""L1/L5 — optional live Redshift access.

Only needed for:
  • `add-table` introspection — pull a table's real columns from svv_columns
    (ground truth, exactly the manual column-dump we did for the GMV table), and
  • EXPLAIN validation — dry-run a generated query without executing it.

Requires `pip install redshift-connector` and REDSHIFT_* set in .env. Everything
else in the system works without this. ALWAYS use a read-only user.
"""
from __future__ import annotations


class RedshiftClient:
    def __init__(self, cfg: dict):
        import redshift_connector  # lazy
        self.conn = redshift_connector.connect(
            host=cfg["host"], port=cfg.get("port", 5439), database=cfg["database"],
            user=cfg["user"], password=cfg["password"],
        )

    def introspect_columns(self, schema: str, table: str) -> list[dict]:
        """Return [{name, type}] from svv_columns, ordered as defined."""
        sql = (
            "SELECT column_name, data_type FROM svv_columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position"
        )
        cur = self.conn.cursor()
        cur.execute(sql, (schema, table))
        rows = cur.fetchall()
        return [{"name": r[0], "type": r[1]} for r in rows]

    def explain(self, sql: str) -> tuple[bool, str]:
        """Run EXPLAIN (no execution). Returns (ok, message)."""
        try:
            cur = self.conn.cursor()
            cur.execute("EXPLAIN " + sql.rstrip().rstrip(";"))
            cur.fetchall()
            return True, "EXPLAIN succeeded — the query plans without error."
        except Exception as e:
            return False, f"EXPLAIN failed: {e}"


def get_redshift(settings) -> "RedshiftClient | None":
    if not settings.has_redshift:
        return None
    try:
        return RedshiftClient(settings.redshift)
    except Exception as e:
        print(f"[redshift] connection unavailable ({e}).")
        return None
