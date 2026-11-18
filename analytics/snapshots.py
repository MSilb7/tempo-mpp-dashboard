"""Load v1 verified ingestion snapshots into an isolated, replayable warehouse.

Offline replay checks consistency with saved RPC evidence, not fresh consensus.
Immutable receipt evidence and acquisition observations are separate from facts.
"""
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from analytics.schema import create_raw
from analytics.workflow import connect, is_snapshot_store, locked, mesh, publish

ROOT = Path(__file__).resolve().parents[1]
MAX_DECIMAL = 10**38 - 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def validate(snapshot):
    content = canonical(snapshot)
    result = subprocess.run(["node", str(ROOT / "scripts/validate-snapshot.mjs")],
        input=content, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError("Snapshot failed offline receipt/canonical-transfer consistency checks")
    acquired = datetime.fromisoformat(snapshot["acquiredAt"].replace("Z", "+00:00"))
    if acquired.utcoffset() is None:
        raise ValueError("Acquisition time must be timezone aware")
    dates = []
    for block in snapshot["rawEvidence"]["blocks"]:
        at = datetime.fromtimestamp(int(block["timestamp"], 16), timezone.utc)
        if at > acquired:
            raise ValueError("Block timestamp exceeds acquisition time")
        dates.append(at.date())
    if not dates or (max(dates) - min(dates)).days > 3660:
        raise ValueError("Snapshot dates missing or exceed 3660-day local bound")
    # Defensive schema envelope: arbitrary external assertions are not accepted
    # through the receipt loader; separate ingestion is required for each source.
    return content, min(dates), max(dates)


def create_store(db, synthetic):
    create_raw(db)
    db.execute("""
        CREATE TABLE raw.store (schema_version INTEGER, synthetic BOOLEAN, built BOOLEAN);
        CREATE TABLE raw.snapshots (
          snapshot_id VARCHAR PRIMARY KEY, manifest VARCHAR NOT NULL,
          start_date DATE NOT NULL, end_date DATE NOT NULL, status VARCHAR NOT NULL,
          publication_id VARCHAR);
        CREATE TABLE raw.movements (
          transfer_id VARCHAR PRIMARY KEY, record VARCHAR NOT NULL,
          included BOOLEAN NOT NULL, exclusion_reason VARCHAR);
        CREATE TABLE raw.transfer_observations (
          snapshot_id VARCHAR NOT NULL, transfer_id VARCHAR NOT NULL,
          PRIMARY KEY(snapshot_id,transfer_id));
        CREATE TABLE raw.receipt_evidence (
          transaction_id VARCHAR PRIMARY KEY, record VARCHAR NOT NULL);
        CREATE TABLE raw.block_evidence (
          block_id VARCHAR PRIMARY KEY, record VARCHAR NOT NULL);
    """)
    db.execute("INSERT INTO raw.store VALUES (1,?,false)", [synthetic])


def conflict_checked_insert(db, table, key_column, key, record):
    # Names are internal constants, never user-provided identifiers.
    previous = db.execute(f"SELECT record FROM raw.{table} WHERE {key_column}=?", [key]).fetchone()
    if previous and previous[0] != record:
        raise ValueError("Conflicting canonical evidence/reorg; replacement requires explicit reconciliation")
    if not previous:
        db.execute(f"INSERT INTO raw.{table} VALUES (?,?)", [key, record])


def load_snapshot(home, path):
    path = Path(path)
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("Snapshot exceeds 128 MiB local import bound")
    snapshot = json.loads(path.read_text())
    content, start, end = validate(snapshot)
    digest = hashlib.sha256(content.encode()).hexdigest()
    with locked(home) as home:
        with connect(home) as db:
            tables = db.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='raw'").fetchone()[0]
            if tables and not is_snapshot_store(db):
                raise ValueError("Demo/legacy warehouse cannot receive snapshots; use a separate fresh --home")
            if not tables:
                create_store(db, snapshot["synthetic"])
            mode = db.execute("SELECT schema_version,synthetic FROM raw.store").fetchone()
            if mode != (1, snapshot["synthetic"]):
                raise ValueError("Cannot mix synthetic and live evidence or incompatible warehouse schemas")
            known = db.execute("SELECT 1 FROM raw.snapshots WHERE snapshot_id=?", [digest]).fetchone()
            if not known:
                old = db.execute("SELECT min(event_date),max(event_date) FROM raw.calendar").fetchone()
                begin = min(start, old[0]) if old[0] else start
                finish = max(end, old[1]) if old[1] else end
                if (finish - begin).days > 3660:
                    raise ValueError("Combined history exceeds 3660-day local bound")
                db.execute("BEGIN")
                try:
                    chain = snapshot["chainId"]
                    for receipt in snapshot["rawEvidence"]["receipts"]:
                        conflict_checked_insert(db, "receipt_evidence", "transaction_id",
                            f"{chain}:{receipt['transactionHash']}", canonical(receipt))
                    for block in snapshot["rawEvidence"]["blocks"]:
                        conflict_checked_insert(db, "block_evidence", "block_id",
                            f"{chain}:{int(block['number'],16)}", canonical(block))
                    for t in snapshot["transfers"]:
                        record = canonical(t)
                        existing = db.execute("SELECT record FROM raw.movements WHERE transfer_id=?", [t["id"]]).fetchone()
                        if existing and existing[0] != record:
                            raise ValueError("Conflicting transfer identity; refusing replacement/double-counting")
                        if not existing:
                            amount = int(t["amountAtomic"])
                            reason = ("non-transfer" if t["movement"] != "transfer" else
                                      "non-mpp-v1" if t["attribution"]["status"] != "mpp-v1" else
                                      "zero-value" if amount == 0 else None)
                            if reason is None and amount > MAX_DECIMAL:
                                raise ValueError("MPP amount exceeds DECIMAL(38,0); snapshot rejected without lossy casting")
                            db.execute("INSERT INTO raw.movements VALUES (?,?,?,?)",
                                [t["id"], record, reason is None, reason])
                            if reason is None:
                                event_date = datetime.fromtimestamp(int(t["timestamp"]), timezone.utc).date()
                                a = t["attribution"]
                                db.execute("INSERT INTO raw.transfers VALUES (?,?,?,?,?,?,?,?,?)", [
                                    t["id"], event_date, f"tempo-{chain}-{a['serverFingerprint']}",
                                    f"{chain}:{t['payer']}", f"{chain}:{t['token']}", t["amountAtomic"],
                                    snapshot["synthetic"], a["clientFingerprint"],
                                    "absent" if a["clientFingerprint"] is None else "unresolved"])
                        db.execute("INSERT INTO raw.transfer_observations VALUES (?,?)", [digest, t["id"]])
                    db.executemany("INSERT OR IGNORE INTO raw.calendar VALUES (?)",
                        [(begin + timedelta(days=i),) for i in range((finish-begin).days+1)])
                    manifest = {k: snapshot[k] for k in ("schemaVersion", "synthetic", "acquiredAt", "source", "chainId", "coverage", "finality")}
                    manifest["snapshot_id"] = digest
                    manifest["evidence_path"] = f"snapshots/{digest}.json"
                    db.execute("INSERT INTO raw.snapshots VALUES (?,?,?,?, 'pending',NULL)",
                        [digest, canonical(manifest), start, end])
                    folder = home / "snapshots"
                    folder.mkdir(exist_ok=True)
                    target = folder / f"{digest}.json"
                    if target.exists() and target.read_text() != content:
                        raise ValueError("Immutable snapshot hash collision/corruption")
                    tmp = folder / f"{digest}.tmp"
                    tmp.write_text(content)
                    tmp.replace(target)
                    db.execute("COMMIT")
                except Exception:
                    db.execute("ROLLBACK")
                    raise
        return build_pending(home)


def build_pending(home):
    """Caller holds writer lock. Restate full bounded observed history initially.

    This intentionally prioritizes replay correctness over incremental efficiency.
    SQLMesh still owns materialization and dependency propagation.
    """
    with connect(home) as db:
        count = db.execute("SELECT count(*) FROM raw.snapshots WHERE status='pending'").fetchone()[0]
        count += db.execute("SELECT count(*) FROM raw.label_changes WHERE status='pending'").fetchone()[0]
        if not count:
            return None
        start, end = db.execute("SELECT min(event_date),max(event_date) FROM raw.calendar").fetchone()
    execution = (end + timedelta(days=1)).isoformat()
    with mesh(home) as ctx:
        # Handles initial tables, expanded dates and model schema changes.
        ctx.plan("prod", execution_time=execution, no_prompts=True, auto_apply=True)
        # Always restate: an interrupted initial publication may already have
        # materialized tables while additional source observations were queued.
        ctx.plan("prod", start=start.isoformat(), end=end.isoformat(), execution_time=execution,
            restate_models=["tempo.enriched_transfers"], no_prompts=True, auto_apply=True)
    publication = publish(home)
    with connect(home) as db:
        db.execute("BEGIN")
        db.execute("UPDATE raw.store SET built=true")
        db.execute("UPDATE raw.snapshots SET status='applied',publication_id=? WHERE status='pending'", [publication])
        db.execute("UPDATE raw.label_changes SET status='applied',publication_id=? WHERE status='pending'", [publication])
        db.execute("COMMIT")
    return publication


def publication_metadata(db):
    mode = db.execute("SELECT synthetic FROM raw.store").fetchone()[0]
    manifests = [json.loads(r[0]) for r in db.execute("SELECT manifest FROM raw.snapshots ORDER BY snapshot_id").fetchall()]
    start, end = db.execute("SELECT min(event_date),max(event_date) FROM raw.calendar").fetchone()
    evidence = []
    for record, included, reason in db.execute("SELECT record,included,exclusion_reason FROM raw.movements ORDER BY transfer_id").fetchall():
        t = json.loads(record)
        observations = [r[0] for r in db.execute("SELECT snapshot_id FROM raw.transfer_observations WHERE transfer_id=? ORDER BY snapshot_id", [t["id"]]).fetchall()]
        evidence.append({"transfer": t, "snapshot_ids": observations,
                         "included_in_mpp_metrics": included, "exclusion_reason": reason})
    acquisitions = [datetime.fromisoformat(m['acquiredAt'].replace('Z', '+00:00')).astimezone(timezone.utc)
                    for m in manifests]
    return {"schema_version": 2, "synthetic": mode,
        "population": "positive-mpp-v1-tagged-transfers",
        "identity_semantics": {"payer": "chain-scoped address, not person",
            "service": "chain-scoped server fingerprint, not resolved operator",
            "token": "chain-scoped token address; atomic units only",
            "originating_interface": "unknown; no client/interface mapping has been established"},
        "coverage": {"from": start.isoformat(), "through": end.isoformat(),
            "scope": "union of explicit receipt/token selections", "complete_for_block_range": False,
            "complete_for_day": False, "complete_for_rolling_window": False,
            "chain_population_denominator": None, "workflow_coverage": None,
            "publication_bias": "Selected receipts, not a representative chain/ecosystem sample.",
            "missing_dates": "Unobserved, never interpreted as zero chain activity.",
            "metrics_interpretation": "Observed selected payments only; no ecosystem DAU/WAU, retention or churn claim."},
        "provenance": {"snapshots": manifests,
            "verification": "Offline replay of saved RPC receipts/blocks; not independent proofs or a fresh finality check.",
            "acquired_from": min(acquisitions).isoformat(),
            "acquired_through": max(acquisitions).isoformat()},
        "transfer_evidence": evidence}
