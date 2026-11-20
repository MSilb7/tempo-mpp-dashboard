"""Durable, single-writer acquisition of bounded discovery windows and receipt batches.

Checkpoints describe work performed, not provider completeness. Network calls are
read-only Node adapters; SQLMesh imports use the existing idempotent loader.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from analytics.snapshots import load_snapshot, canonical
from analytics.workflow import locked

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_config(config):
    allowed = {'chainId', 'fromBlock', 'toBlock', 'tokens', 'windowBlocks', 'batchSize', 'maxPages', 'observationKey'}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError('Unknown acquisition config fields')
    cfg = dict(windowBlocks=100, batchSize=25, maxPages=10, observationKey='initial') | config
    if not isinstance(cfg['observationKey'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', cfg['observationKey']):
        raise ValueError('Invalid observationKey')
    if cfg.get('chainId') not in ('4217', '42431'):
        raise ValueError('Expected Tempo chainId string')
    for key, low, high in [('fromBlock', 0, 2**53-1), ('toBlock', 0, 2**53-1),
                           ('windowBlocks', 1, 1000), ('batchSize', 1, 100), ('maxPages', 1, 20)]:
        if type(cfg.get(key)) is not int or not low <= cfg[key] <= high:
            raise ValueError(f'Invalid {key}')
    if not 0 <= cfg['toBlock']-cfg['fromBlock'] < 10000:
        raise ValueError('Select an inclusive range of at most 10000 blocks')
    tokens = cfg.get('tokens')
    if not isinstance(tokens, list) or not 1 <= len(tokens) <= 20 or any(
            not isinstance(t, str) or not re.fullmatch(r'0x20[cC]0[0-9a-fA-F]{36}', t) for t in tokens):
        raise ValueError('Expected 1–20 native TIP-20 tokens')
    cfg['tokens'] = sorted(set(t.lower() for t in tokens))
    if (cfg['toBlock']-cfg['fromBlock']) // cfg['windowBlocks'] >= 1000:
        raise ValueError('At most 1000 windows per job')
    return cfg


class NodeSource:
    synthetic = False

    def __init__(self):
        self.endpoint = os.environ.get('TEMPO_RPC_URL', '')
        try:
            url = urlsplit(self.endpoint)
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError()
            # Only the origin is persisted; malformed URL errors must not echo input.
            host = f'[{url.hostname}]' if ':' in url.hostname else url.hostname.encode('idna').decode('ascii')
            self.origin = f'https://{host}' + (f':{url.port}' if url.port not in (None, 443) else '')
        except (ValueError, UnicodeError):
            raise ValueError('TEMPO_RPC_URL requires a valid HTTPS endpoint without user credentials') from None
        self.last_discovery = 0

    def call(self, operation, config=None, selection=None):
        if operation == 'discover':
            time.sleep(max(0, 3.1 - (time.monotonic()-self.last_discovery)))
        try:
            result = subprocess.run(['node', str(ROOT/'scripts/acquisition-source.mjs')],
                input=json.dumps(dict(operation=operation, config=config, selection=selection)),
                text=True, capture_output=True, timeout=1800,
                env={**os.environ, 'TEMPO_RPC_URL': self.endpoint})
            if result.returncode:
                raise ValueError('Acquisition failed; resume after checking provider access, finalized bounds and window budgets')
            return json.loads(result.stdout)
        finally:
            if operation == 'discover':
                self.last_discovery = time.monotonic()


def database(home):
    db = sqlite3.connect(home/'checkpoints.sqlite3')
    os.chmod(home/'checkpoints.sqlite3', 0o600)
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (0, 1):
        db.close()
        raise ValueError('Unsupported checkpoint schema version')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, config TEXT NOT NULL, source TEXT NOT NULL,
        synthetic INTEGER NOT NULL, warehouse TEXT NOT NULL,
        anchor TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS windows (
        job_id TEXT NOT NULL, seq INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
        discovery TEXT, PRIMARY KEY(job_id,seq));
      CREATE TABLE IF NOT EXISTS batches (
        job_id TEXT NOT NULL, window_seq INTEGER NOT NULL, seq INTEGER NOT NULL,
        selection TEXT NOT NULL, snapshot_path TEXT, snapshot_sha TEXT, imported INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(job_id,window_seq,seq));
    ''')
    db.execute('PRAGMA user_version=1')
    return db


def validate_discovery(result, config):
    selection, info = result['selection'], result['discovery']
    hashes = selection['transactionHashes']
    if (selection['chainId'] != config['chainId'] or selection['tokens'] != config['tokens']
            or not isinstance(hashes, list) or len(hashes) > 100
            or any(not isinstance(h, str) or not re.fullmatch(r'0x[0-9a-f]{64}',h) for h in hashes)
            or len(set(hashes)) != len(hashes)):
        raise ValueError('Discovery selection differs from requested scope')
    if (info['source'] != 'https://api.tempo.xyz/v1/transfers'
            or info['fromBlock'] != config['fromBlock'] or info['toBlock'] != config['toBlock']
            or info['paginationExhausted'] is not True or info['chainCompletenessVerified'] is not False
            or type(info['pages']) is not int or not 1 <= info['pages'] <= config['maxPages']
            or type(info['apiRows']) is not int or not len(hashes) <= info['apiRows'] <= info['pages']*50):
        raise ValueError('Invalid discovery checkpoint coverage')
    acquired = datetime.fromisoformat(result['acquiredAt'].replace('Z','+00:00'))
    if acquired.utcoffset() is None:
        raise ValueError('Discovery acquisition time must be timezone aware')


def write_snapshot(home, snapshot):
    content = canonical(snapshot).encode()
    digest = hashlib.sha256(content).hexdigest()
    folder = home/'snapshots'; folder.mkdir(exist_ok=True)
    target = folder/f'{digest}.json'
    if target.exists():
        if target.read_bytes() != content:
            raise ValueError('Checkpoint snapshot corrupted')
    else:
        temp = folder/f'{digest}.tmp'
        with temp.open('wb') as handle:
            os.chmod(temp, 0o600)
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        temp.replace(target)
        fd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return str(target.relative_to(home)), digest


def start(home, warehouse, config, source, **options):
    cfg = validate_config(config)
    warehouse = Path(warehouse).resolve()
    home = Path(home).resolve()
    if home == warehouse:
        raise ValueError('Checkpoint home and warehouse must differ')
    # Deterministic identity makes resubmission of an identical job resumable.
    identity = dict(config=cfg, source=source.origin, synthetic=source.synthetic, warehouse=str(warehouse))
    job_id = hashlib.sha256(canonical(identity).encode()).hexdigest()
    with locked(home) as home:
        db = database(home)
        try:
            if not db.execute('SELECT 1 FROM jobs WHERE id=?', [job_id]).fetchone():
                anchor = source.call('anchor', config=cfg)
                with db:
                    db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',
                        [job_id, canonical(cfg), source.origin, source.synthetic, str(warehouse), canonical(anchor), now(), 'pending'])
                    for seq, begin in enumerate(range(cfg['fromBlock'], cfg['toBlock']+1, cfg['windowBlocks'])):
                        db.execute('INSERT INTO windows VALUES (?,?,?,?,NULL)',
                            [job_id, seq, begin, min(begin+cfg['windowBlocks']-1, cfg['toBlock'])])
            return run(db, home, job_id, source, **options)
        finally:
            db.close()


def resume(home, job_id, source, **options):
    with locked(home) as home:
        db = database(home)
        try:
            return run(db, home, job_id, source, **options)
        finally:
            db.close()


def run(db, home, job_id, source, importer=load_snapshot, after_import=None):
    job = db.execute('SELECT * FROM jobs WHERE id=?', [job_id]).fetchone()
    if not job:
        raise ValueError('Unknown checkpoint job')
    if (job['source'], bool(job['synthetic'])) != (source.origin, source.synthetic):
        raise ValueError('Resume source/mode differs from pinned job')
    cfg = json.loads(job['config'])
    if job['status'] == 'complete':
        return coverage(db, job_id)
    anchor = source.call('anchor', config=cfg)
    if anchor['endBlockHash'] != json.loads(job['anchor'])['endBlockHash']:
        raise ValueError('Pinned range-end block changed; explicit reorg reconciliation required')
    for window in db.execute('SELECT * FROM windows WHERE job_id=? ORDER BY seq', [job_id]).fetchall():
        if window['discovery'] is None:
            config = {k: cfg[k] for k in ('chainId','tokens','maxPages')}
            config.update(fromBlock=window['start'], toBlock=window['end'])
            discovery = source.call('discover', config=config)
            validate_discovery(discovery, config)
            hashes = discovery['selection']['transactionHashes']
            with db:
                db.execute('UPDATE windows SET discovery=? WHERE job_id=? AND seq=?',
                    [canonical(discovery), job_id, window['seq']])
                for seq, offset in enumerate(range(0, len(hashes), cfg['batchSize'])):
                    selection = dict(chainId=cfg['chainId'], tokens=cfg['tokens'], transactionHashes=hashes[offset:offset+cfg['batchSize']])
                    db.execute('INSERT INTO batches(job_id,window_seq,seq,selection) VALUES (?,?,?,?)',
                        [job_id, window['seq'], seq, canonical(selection)])
        else:
            discovery = json.loads(window['discovery'])
        batches = db.execute('SELECT * FROM batches WHERE job_id=? AND window_seq=? ORDER BY seq', [job_id,window['seq']]).fetchall()
        for batch in batches:
            if batch['imported']:
                continue
            path = batch['snapshot_path']
            digest = batch['snapshot_sha']
            if path is None:
                selection = json.loads(batch['selection'])
                snapshot = source.call('ingest', selection=selection)
                receipts = snapshot['rawEvidence']['receipts']
                if (snapshot['chainId'] != cfg['chainId']
                        or snapshot['coverage']['tokenAllowlist'] != cfg['tokens']
                        or sorted(r['transactionHash'].lower() for r in receipts) != sorted(selection['transactionHashes'])):
                    raise ValueError('Receipt batch does not match checkpoint selection')
                if snapshot['synthetic'] != bool(job['synthetic']) or snapshot['source'] != job['source']:
                    raise ValueError('Snapshot source/mode differs from pinned job')
                if any(not window['start'] <= int(r['blockNumber'],16) <= window['end'] for r in snapshot['rawEvidence']['receipts']):
                    raise ValueError('Receipt outside discovery window')
                snapshot['discoveryContext'] = dict(job_id=job_id, window_seq=window['seq'],
                    discovery_source=discovery['discovery']['source'],
                    from_block=window['start'], to_block=window['end'],
                    discovered_at=discovery['acquiredAt'], pages=discovery['discovery']['pages'],
                    api_rows=discovery['discovery']['apiRows'], candidate_transactions=len(discovery['selection']['transactionHashes']),
                    pagination_exhausted=True, chain_completeness_verified=False)
                path, digest = write_snapshot(home, snapshot)
                with db:
                    db.execute('UPDATE batches SET snapshot_path=?,snapshot_sha=? WHERE job_id=? AND window_seq=? AND seq=?',
                        [path, digest, job_id, window['seq'], batch['seq']])
            snapshot_path = home/path
            if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != digest:
                raise ValueError('Checkpoint snapshot corrupted; refusing import')
            importer(Path(job['warehouse']), snapshot_path)
            if after_import:
                after_import()  # Crash-injection seam: publication succeeded, acknowledgment did not.
            with db:
                db.execute('UPDATE batches SET imported=1 WHERE job_id=? AND window_seq=? AND seq=?',
                    [job_id, window['seq'], batch['seq']])
    with db:
        db.execute("UPDATE jobs SET status='complete' WHERE id=?", [job_id])
    return coverage(db, job_id)


def coverage(db, job_id):
    job = db.execute('SELECT * FROM jobs WHERE id=?', [job_id]).fetchone()
    if not job:
        raise ValueError('Unknown checkpoint job')
    windows = []
    for window in db.execute('SELECT * FROM windows WHERE job_id=? ORDER BY seq', [job_id]).fetchall():
        counts = db.execute('SELECT count(*),coalesce(sum(snapshot_path IS NOT NULL),0),coalesce(sum(imported),0) FROM batches WHERE job_id=? AND window_seq=?', [job_id,window['seq']]).fetchone()
        discovery = json.loads(window['discovery']) if window['discovery'] else None
        windows.append(dict(from_block=window['start'], to_block=window['end'], discovery=discovery,
            receipt_batches=counts[0], verified_batches=counts[1], imported_batches=counts[2],
            work_complete=discovery is not None and counts[0]==counts[2]))
    return dict(job_id=job_id, status=job['status'], synthetic=bool(job['synthetic']), source=job['source'],
        config=json.loads(job['config']), anchor=json.loads(job['anchor']), windows=windows,
        complete_for_block_range=False, complete_for_day=False,
        limitation='Completed work covers discovered candidates and selected tokens only. Empty windows and exhausted pagination do not prove chain completeness. Checkpoints retain as-acquired finality; completed imports are not reverified on resume.')



def status(home):
    """Observe committed progress without waiting on the acquisition writer lock."""
    path = Path(home).resolve()/'checkpoints.sqlite3'
    if not path.is_file():
        raise ValueError('Checkpoint database not found; status does not create a new store')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('Unsupported checkpoint schema version')
        # One consistent read transaction across jobs/windows/batches.
        db.execute('BEGIN')
        return [coverage(db, row[0]) for row in db.execute('SELECT id FROM jobs ORDER BY created_at').fetchall()]
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('start'); create.add_argument('config', type=Path); create.add_argument('--warehouse', type=Path, required=True)
    retry = commands.add_parser('resume'); retry.add_argument('job_id')
    commands.add_parser('status')
    args = parser.parse_args()
    if args.command == 'start':
        result = start(args.home, args.warehouse, json.loads(args.config.read_text()), NodeSource())
    elif args.command == 'resume':
        result = resume(args.home, args.job_id, NodeSource())
    else:
        result = status(args.home)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
