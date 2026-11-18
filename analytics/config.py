import os
from pathlib import Path

from sqlmesh.core.config import Config, GatewayConfig, ModelDefaultsConfig
from sqlmesh.core.config.connection import DuckDBConnectionConfig


def make_config(home: Path, start="2026-01-01") -> Config:
    home.mkdir(parents=True, exist_ok=True)
    return Config(
        gateways={"local": GatewayConfig(connection=DuckDBConnectionConfig(
            database=str(home / "warehouse.duckdb"), concurrent_tasks=1,
            connector_config={"TimeZone": "UTC"}))},
        default_gateway="local",
        model_defaults=ModelDefaultsConfig(dialect="duckdb", start=start),
        disable_anonymized_analytics=True,
        cache_dir=str(home / "cache"),
    )


config = make_config(Path(os.environ.get("TEMPO_ANALYTICS_DIR",
    Path(__file__).resolve().parents[1] / ".local" / "analytics")).resolve())
