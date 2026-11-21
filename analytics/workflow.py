"""Single-writer synthetic pilot with durable pending label changes.

No wallet, RPC or network calls. SQLMesh owns downstream execution. We own
label validation, impact dates, retry state and the publication gate.
"""
import fcntl
import hashlib
import json
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlmesh import Context

from analytics.audits import audit_models
from analytics.backend import Backend, connect, table_count, assert_fresh
from analytics.config import make_config
from analytics.schema import create_raw

PROJECT = Path(__file__).resolve().parent
END = "2026-01-10"
EXECUTION_TIME = "2026-01-11"


@contextmanager
def locked(home):
    home = Path(home).resolve()
    home.mkdir(parents=True, exist_ok=True)
    with (home / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        backend = Backend.from_env(home)
        backend.require_execution()
        backend.bind(home)
        yield home



@contextmanager
def mesh(home):
    start = "2026-01-01"
    with connect(home) as db:
        start = db.execute("SELECT min(event_date) FROM raw.calendar").fetchone()[0].isoformat()
        if not is_snapshot_store(db):
            # Additive compatibility for synthetic warehouses from the first pilot.
            db.execute("ALTER TABLE raw.transfers ADD COLUMN IF NOT EXISTS client_fingerprint VARCHAR")
            db.execute("ALTER TABLE raw.transfers ADD COLUMN IF NOT EXISTS interface_status VARCHAR DEFAULT 'absent'")
    Backend.from_env(home).require_execution()
    ctx = Context(paths=PROJECT, config=make_config(home, start=start))
    try:
        yield ctx
    finally:
        ctx.close()


def is_snapshot_store(db):
    return bool(table_count(db, table='snapshots'))


def rows(db, sql):
    result = db.execute(sql)
    names = [c[0] for c in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def encoded(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def publish(home):
    """Audit all history; latest.json is the serving boundary, not live tables."""
    with connect(home) as db:
        raw = db.execute("SELECT count(*), sum(amount_atomic) FROM raw.transfers").fetchone()
        fact = db.execute("SELECT count(*), sum(amount_atomic), count(DISTINCT transfer_id) FROM tempo.enriched_transfers").fetchone()
        daily = db.execute("SELECT coalesce(sum(payment_count),0), sum(amount_atomic) FROM tempo.daily_metrics").fetchone()
        if raw != fact[:2] or fact[0] != fact[2] or raw != daily:
            raise ValueError("Conservation/fanout audit failed; previous publication retained")
        by_token = db.execute("SELECT token,count(*),sum(amount_atomic) FROM raw.transfers GROUP BY token ORDER BY token").fetchall()
        model_by_token = db.execute("SELECT token,sum(payment_count),sum(amount_atomic) FROM tempo.daily_metrics GROUP BY token ORDER BY token").fetchall()
        if by_token != model_by_token:
            raise ValueError("Per-token conservation audit failed")
        # Compare every fact, not just totals (two swapped amounts could cancel).
        mismatch = db.execute("""
          SELECT count(*) FROM (
            (SELECT transfer_id,event_date,service_id,payer,token,amount_atomic,synthetic,client_fingerprint,interface_status FROM raw.transfers
             EXCEPT SELECT transfer_id,event_date,service_id,payer,token,amount_atomic,synthetic,client_fingerprint,interface_status FROM tempo.enriched_transfers)
            UNION ALL
            (SELECT transfer_id,event_date,service_id,payer,token,amount_atomic,synthetic,client_fingerprint,interface_status FROM tempo.enriched_transfers
             EXCEPT SELECT transfer_id,event_date,service_id,payer,token,amount_atomic,synthetic,client_fingerprint,interface_status FROM raw.transfers)
          )
        """).fetchone()[0]
        if mismatch:
            raise ValueError("Raw fact preservation audit failed")
        audit_models(db, rows)
        first_date, last_date = db.execute("SELECT min(event_date),max(event_date) FROM raw.calendar").fetchone()
        payload = {"schema_version": 1, "synthetic": True,
            "coverage": {"from": first_date.isoformat(), "through": last_date.isoformat(), "scope": "synthetic fixture only"},
            "labels": rows(db, "SELECT * FROM raw.service_labels ORDER BY assertion_id"),
            "daily": rows(db, "SELECT * FROM tempo.daily_metrics ORDER BY event_date, token, category"),
            "rolling_7d": rows(db, "SELECT * FROM tempo.rolling_7d ORDER BY event_date, token, category")}
        if is_snapshot_store(db):
            from analytics.snapshots import publication_metadata
            payload.update(publication_metadata(db))
    content = json.dumps(payload, default=encoded, sort_keys=True, indent=2) + "\n"
    digest = hashlib.sha256(content.encode()).hexdigest()
    folder = home / "publications"
    folder.mkdir(exist_ok=True)
    target = folder / f"{digest}.json"
    if not target.exists():
        with target.open("x") as f:
            f.write(content)
    # Immutable publication first; only a validated complete artifact is exposed.
    tmp = home / "latest.json.tmp"
    tmp.write_text(content)
    tmp.replace(home / "latest.json")
    return digest


def init_demo(home):
    with locked(home) as home:
        assert_fresh(home)
        with connect(home) as db:
            create_raw(db)
            db.executemany("INSERT INTO raw.transfers (transfer_id,event_date,service_id,payer,token,amount_atomic,synthetic) VALUES (?,?,?,?,?,?,true)", [
                ("t1", "2026-01-01", "synthetic-service-a", "payer-a", "token-a", "9007199254740993"),
                ("t2", "2026-01-02", "synthetic-service-a", "payer-a", "token-a", "200"),
                ("t3", "2026-01-03", "synthetic-service-a", "payer-b", "token-a", "300"),
                ("t4", "2026-01-03", "synthetic-service-b", "payer-c", "token-a", "400"),
                ("t5", "2026-01-04", "synthetic-service-a", "payer-b", "token-a", "500"),
                ("t6", "2026-01-08", "synthetic-service-b", "payer-c", "token-a", "600"),
            ])
            db.executemany("INSERT INTO raw.calendar VALUES (?)",
                [(date(2026, 1, 1) + timedelta(days=i),) for i in range(10)])
        with mesh(home) as ctx:
            ctx.plan("prod", execution_time=EXECUTION_TIME,
                no_prompts=True, auto_apply=True)
        return publish(home)


def validate_label(label):
    keys = {"assertion_id", "service_id", "category", "valid_from", "valid_to",
        "recorded_at", "evidence_level", "source"}
    if not isinstance(label, dict) or set(label) != keys:
        raise ValueError("Label must contain exactly the documented assertion fields")
    for key in ("assertion_id", "service_id", "category"):
        if not isinstance(label[key], str) or not re.fullmatch(r"[a-z0-9_-]{1,100}", label[key]):
            raise ValueError(f"Invalid {key}")
    if label["category"] == "unknown":
        raise ValueError("unknown is reserved for unresolved labels")
    if label["evidence_level"] not in ("operator-reported", "model-inferred"):
        raise ValueError("Labels cannot be promoted to chain facts")
    if not isinstance(label["source"], str) or not label["source"].strip() or len(label["source"]) > 1000:
        raise ValueError("Source required")
    start = date.fromisoformat(label["valid_from"])
    end = date.fromisoformat(label["valid_to"]) if label["valid_to"] is not None else None
    if end is not None and end <= start:
        raise ValueError("valid_to must be after valid_from (exclusive)")
    recorded = datetime.fromisoformat(label["recorded_at"])
    if recorded.utcoffset() is None:
        raise ValueError("recorded_at requires a timezone")
    return start, end


def enqueue(home, label):
    """Append label + durable pending work together. Caller holds writer lock."""
    start, end = validate_label(label)
    payload = json.dumps(label, sort_keys=True)
    with connect(home) as db:
        existing = db.execute("SELECT payload,status FROM raw.label_changes WHERE assertion_id=?",
            [label["assertion_id"]]).fetchone()
        if existing:
            if existing[0] != payload:
                raise ValueError("Assertion ID already exists with different content")
            return existing[1]
        overlap = db.execute("""SELECT count(*) FROM raw.service_labels
          WHERE service_id=? AND (valid_to IS NULL OR valid_to>?)
          AND (?::DATE IS NULL OR valid_from<?::DATE)""",
          [label["service_id"], start, end, end]).fetchone()[0]
        if overlap:
            raise ValueError("Overlapping label interval; explicit conflict resolution is not implemented")
        affected = db.execute("""SELECT min(event_date),max(event_date) FROM raw.transfers
          WHERE service_id=? AND event_date>=? AND (?::DATE IS NULL OR event_date<?::DATE)""",
          [label["service_id"], start, end, end]).fetchone()
        if affected[0] is None:
            raise ValueError("No affected fixture transfers; future-only label ingestion is not implemented")
        db.execute("BEGIN")
        try:
            db.execute("INSERT INTO raw.service_labels VALUES (?,?,?,?,?,?,?,?)", [label[k] for k in
                ("assertion_id", "service_id", "category", "valid_from", "valid_to", "recorded_at", "evidence_level", "source")])
            db.execute("INSERT INTO raw.label_changes VALUES (?,?,?,?, 'pending',NULL)",
                [label["assertion_id"], payload, *affected])
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return "pending"


def drain(home):
    """Replay pending intervals after failure; conservative union covers all changes."""
    with connect(home) as db:
        pending = db.execute("SELECT min(start_date),max(end_date) FROM raw.label_changes WHERE status='pending'").fetchone()
    with connect(home) as db:
        snapshots = is_snapshot_store(db)
    if snapshots:
        from analytics.snapshots import build_pending
        return build_pending(home)
    if pending[0] is None:
        return None
    with connect(home) as db:
        execution = (db.execute("SELECT max(event_date) FROM raw.calendar").fetchone()[0] + timedelta(days=1)).isoformat()
    with mesh(home) as ctx:
        ctx.plan("prod", execution_time=execution, no_prompts=True, auto_apply=True)
        plan = ctx.plan("prod", start=pending[0].isoformat(), end=pending[1].isoformat(),
            execution_time=execution, restate_models=["tempo.enriched_transfers"],
            no_prompts=True, auto_apply=True)
        if not plan.restatements:
            raise RuntimeError("Expected SQLMesh restatement was not scheduled")
    publication = publish(home)
    with connect(home) as db:
        db.execute("UPDATE raw.label_changes SET status='applied',publication_id=? WHERE status='pending'", [publication])
    return publication


def ingest_label(home, label):
    with locked(home) as home:
        enqueue(home, label)
        return drain(home)


def resume(home):
    with locked(home) as home:
        return drain(home)
