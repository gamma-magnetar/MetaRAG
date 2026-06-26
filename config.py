"""Settings: load config.yaml and .env, resolve paths against the project root."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()  # read .env if present
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent  # project root (folder above app/)


@dataclass
class Settings:
    embedding_model: str = "gemini-embedding-001"
    generation_model: str = "gemini-2.5-flash"
    generation_temperature: float = 0.1
    top_k: int = 8
    candidate_k: int = 30
    rrf_k: int = 60
    dense_dim_fallback: int = 512
    registry_dir: str = "registry"
    index_dir: str = "data/index"
    databook_path: str = "outputs/DATABOOK.md"

    # secrets / env (not stored in config.yaml)
    gemini_api_key: str | None = field(default=None, repr=False)
    redshift: dict = field(default_factory=dict, repr=False)

    # ---- resolved absolute paths ----
    @property
    def registry_path(self) -> Path:
        return ROOT / self.registry_dir

    @property
    def index_path(self) -> Path:
        return ROOT / self.index_dir

    @property
    def databook_file(self) -> Path:
        return ROOT / self.databook_path

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_redshift(self) -> bool:
        r = self.redshift
        return all(r.get(k) for k in ("host", "database", "user", "password"))


def load_settings(config_file: str | os.PathLike | None = None) -> Settings:
    cfg_path = Path(config_file) if config_file else ROOT / "config.yaml"
    data = {}
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text()) or {}
    s = Settings(**{k: v for k, v in data.items() if k in Settings.__dataclass_fields__})
    s.gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    s.redshift = {
        "host": os.getenv("REDSHIFT_HOST"),
        "port": int(os.getenv("REDSHIFT_PORT", "5439")),
        "database": os.getenv("REDSHIFT_DATABASE"),
        "user": os.getenv("REDSHIFT_USER"),
        "password": os.getenv("REDSHIFT_PASSWORD"),
    }
    return s
