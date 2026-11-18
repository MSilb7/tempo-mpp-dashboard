"""Local SQLMesh pilot; all bootstrap data is synthetic."""
import os
from pathlib import Path

# Set before importing SQLMesh's Python API (config alone is insufficient).
os.environ["SQLMESH__DISABLE_ANONYMIZED_ANALYTICS"] = "true"
os.environ.setdefault("SQLMESH_HOME", str(Path(__file__).resolve().parents[1] / ".local" / "sqlmesh"))
