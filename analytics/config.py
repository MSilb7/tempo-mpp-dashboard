import os
from pathlib import Path

from sqlmesh.core.config import Config, GatewayConfig, ModelDefaultsConfig
from analytics.backend import Backend


def make_config(home: Path, start="2026-01-01", backend=None) -> Config:
    home.mkdir(parents=True, exist_ok=True)
    backend = backend or Backend.from_env(home)
    connection, state = backend.sqlmesh_connections(home)
    return Config(
        gateways={"local": GatewayConfig(connection=connection, state_connection=state)},
        default_gateway="local",
        model_defaults=ModelDefaultsConfig(dialect="duckdb", start=start),
        disable_anonymized_analytics=True,
        cache_dir=str(home / "cache"),
    )


# SQLMesh's config discovery must remain offline and local. Workflow callers pass
# an explicit per-home config; importing this module must never select a remote.
_default_home = Path(os.environ.get("TEMPO_ANALYTICS_DIR",
    Path(__file__).resolve().parents[1] / ".local" / "analytics")).resolve()
config = make_config(_default_home, backend=Backend('duckdb', str(_default_home/'warehouse.duckdb')))
