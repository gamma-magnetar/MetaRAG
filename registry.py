"""L0 — the registry: the structured source of truth.

Six YAML files under registry/ : tables, joins, rules, glossary, dictionaries,
golden_queries. Everything downstream (the search index, the DATABOOK) is rendered
from here, so edits land in one place and both regenerate.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml

FILES = ["tables", "joins", "rules", "glossary", "dictionaries", "golden_queries"]


@dataclass
class Registry:
    tables: list
    joins: list
    rules: list
    glossary: list
    dictionaries: dict
    golden_queries: list
    path: Path

    def table(self, name: str) -> dict | None:
        """Find a table card by 'table' or 'schema.table' (case-insensitive)."""
        name = name.lower()
        for t in self.tables:
            if t["table"].lower() == name or f"{t['schema']}.{t['table']}".lower() == name:
                return t
        return None

    def table_names(self) -> set[str]:
        names = set()
        for t in self.tables:
            names.add(t["table"].lower())
            names.add(f"{t['schema']}.{t['table']}".lower())
        return names


def load_registry(registry_dir: Path) -> Registry:
    data = {}
    for name in FILES:
        fp = Path(registry_dir) / f"{name}.yaml"
        data[name] = yaml.safe_load(fp.read_text()) if fp.exists() else ([] if name != "dictionaries" else {})
    return Registry(path=Path(registry_dir), **data)


def save_tables(registry_dir: Path, tables: list) -> None:
    """Persist the tables list back to registry/tables.yaml (used by `add-table`)."""
    fp = Path(registry_dir) / "tables.yaml"
    fp.write_text(yaml.safe_dump(tables, sort_keys=False, allow_unicode=True, width=100))
