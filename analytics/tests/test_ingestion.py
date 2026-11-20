from contextlib import closing
import os
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analytics.ingestion import start, resume, database, coverage, validate_config, status, NodeSource
from analytics.snapshots import load_snapshot
from analytics.workflow import connect
from analytics.tests.test_snapshots import snapshot

TOKEN = '0x20c0' + '0'*35 + '1'
CONFIG = dict(chainId='4217', fromBlock=1001, toBlock=1003, tokens=[TOKEN], windowBlocks=1, batchSize=1)


class FixtureSource:
    synthetic = True
    origin = 'https://rpc.synthetic.example'

    def __init__(self):
        self.calls = []
        self.fail = None
        self.changed = False

    def call(self, operation, config=None, selection=None):
        self.calls.append((operation, config, selection))
        if self.fail == operation:
            raise RuntimeError('injected source interruption')
        if operation == 'anchor':
            return dict(endBlockHash='0x' + ('ff' if self.changed else 'ab')*32,
                        finalizedBlock='2000', finalizedHash='0x'+'ef'*32, source=self.origin)
        if operation == 'discover':
            ids = [i for i in (1,2,3) if config['fromBlock'] <= 1000+i <= config['toBlock']]
            hashes = ['0x'+format(i,'064x') for i in ids]
            return dict(schemaVersion=1, acquiredAt='2026-01-31T00:00:00Z',
                selection=dict(chainId=config['chainId'], tokens=config['tokens'], transactionHashes=hashes),
                discovery=dict(source='https://api.tempo.xyz/v1/transfers', fromBlock=config['fromBlock'],
                    toBlock=config['toBlock'], pages=1, apiRows=len(ids), paginationExhausted=True,
                    chainCompletenessVerified=False))
        return snapshot(ids=[int(h,16) for h in selection['transactionHashes']])


class CheckpointTests(unittest.TestCase):
    def job(self, home):
        with closing(sqlite3.connect(home/'checkpoints.sqlite3')) as db:
            return db.execute('SELECT id FROM jobs').fetchone()[0]

    def test_crash_after_publication_resume_and_overlapping_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); home = folder/'checkpoints'; warehouse=folder/'warehouse'
            source = FixtureSource()
            # Hard exit bypasses finally/connection cleanup, like a process crash.
            child = subprocess.run([sys.executable, '-c',
                "import os,sys; from pathlib import Path; "
                "from analytics.ingestion import start; "
                "from analytics.tests.test_ingestion import FixtureSource,CONFIG; "
                "start(Path(sys.argv[1]),Path(sys.argv[2]),CONFIG,FixtureSource(),after_import=lambda: os._exit(23))",
                str(home), str(warehouse)], capture_output=True, text=True)
            self.assertEqual(child.returncode, 23, child.stderr)
            with connect(warehouse) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM raw.transfers').fetchone()[0], 1)
            # Replays the saved snapshot (no re-acquisition), then continues later windows.
            before_ingest = sum(c[0]=='ingest' for c in source.calls)
            result = resume(home, self.job(home), source)
            self.assertEqual(sum(c[0]=='ingest' for c in source.calls)-before_ingest, 2)
            self.assertEqual(result['status'], 'complete')
            self.assertFalse(result['complete_for_block_range'])
            self.assertTrue(all(w['work_complete'] for w in result['windows']))
            out = json.loads((warehouse/'latest.json').read_text())
            self.assertEqual(sum(r['payment_count'] for r in out['daily']), 3)
            self.assertEqual(sum(int(r['amount_atomic']) for r in out['daily']), 600)
            self.assertTrue(all('discovery_context' in m for m in out['provenance']['snapshots']))
            calls = len(source.calls)
            stable = (warehouse/'latest.json').read_bytes()
            start(home, warehouse, CONFIG, source)
            self.assertEqual(len(source.calls), calls)
            self.assertEqual((warehouse/'latest.json').read_bytes(), stable)
            # Different range/window layout observes existing payments again.
            start(home, warehouse, {**CONFIG, 'fromBlock':1002, 'windowBlocks':2}, source)
            # Explicit repeat observation supports indexer-lag reconciliation later.
            start(home, warehouse, {**CONFIG, 'observationKey':'recheck-1'}, source)
            newer = json.loads((warehouse/'latest.json').read_text())
            self.assertEqual(newer['daily'], out['daily'])
            self.assertEqual(newer['rolling_7d'], out['rolling_7d'])
            with connect(warehouse) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM raw.transfers').fetchone()[0], 3)
                self.assertEqual(db.execute('SELECT count(*) FROM raw.transfer_observations').fetchone()[0], 8)

    def test_discovery_checkpoint_empty_window_and_import_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); home=folder/'cp'; warehouse=folder/'db'; source=FixtureSource()
            source.fail='ingest'
            cfg={**CONFIG, 'fromBlock':1003, 'toBlock':1004}
            with self.assertRaisesRegex(RuntimeError, 'interruption'):
                start(home, warehouse, cfg, source)
            job=self.job(home)
            with closing(database(home)) as db:
                status=coverage(db, job)
            self.assertFalse(status['windows'][0]['work_complete'])
            self.assertEqual(status['windows'][0]['verified_batches'], 0)
            source.fail=None
            def bad_import(*args):
                raise RuntimeError('injected import failure')
            with self.assertRaisesRegex(RuntimeError, 'import failure'):
                resume(home, job, source, importer=bad_import)
            with closing(database(home)) as db:
                self.assertEqual(coverage(db,job)['windows'][0]['verified_batches'],1)
            ingests=sum(c[0]=='ingest' for c in source.calls)
            result=resume(home, job, source)
            self.assertEqual(sum(c[0]=='ingest' for c in source.calls),ingests)
            self.assertEqual(sum(c[0]=='discover' for c in source.calls),2)
            empty=result['windows'][1]
            self.assertTrue(empty['work_complete'])
            self.assertEqual(empty['receipt_batches'],0)
            self.assertFalse(result['complete_for_day'])

    def test_interrupted_discovery_source_reorg_and_corruption_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); home=folder/'cp'; source=FixtureSource()
            source.fail='discover'
            with self.assertRaises(RuntimeError):
                start(home,folder/'db',CONFIG,source)
            job=self.job(home)
            with closing(database(home)) as db:
                self.assertIsNone(coverage(db,job)['windows'][0]['discovery'])
            source.fail=None; source.changed=True
            with self.assertRaisesRegex(ValueError,'block changed'):
                resume(home,job,source)
            source.changed=False; source.origin='https://different.example'
            with self.assertRaisesRegex(ValueError,'source/mode'):
                resume(home,job,source)
            source.origin='https://rpc.synthetic.example'
            with self.assertRaises(RuntimeError):
                resume(home,job,source,importer=lambda *args: (_ for _ in ()).throw(RuntimeError('stop')))
            with closing(database(home)) as db:
                path=db.execute('SELECT snapshot_path FROM batches WHERE snapshot_path IS NOT NULL').fetchone()[0]
            (home/path).write_text('{}')
            with self.assertRaisesRegex(ValueError,'corrupted'):
                resume(home,job,source)

    def test_discovery_and_snapshot_context_cannot_claim_complete_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); home=folder/'cp'; source=FixtureSource()
            original_call=source.call
            def invalid(operation, **kwargs):
                value=original_call(operation, **kwargs)
                if operation=='discover':
                    value['discovery']['chainCompletenessVerified']=True
                return value
            source.call=invalid
            with self.assertRaisesRegex(ValueError,'coverage'):
                start(home,folder/'db',CONFIG,source)
            with closing(database(home)) as db:
                self.assertIsNone(coverage(db,self.job(home))['windows'][0]['discovery'])
            source.call=original_call
            resume(home,self.job(home),source)
            publication=(folder/'db/latest.json').read_bytes()
            with closing(database(home)) as db:
                path=db.execute('SELECT snapshot_path FROM batches LIMIT 1').fetchone()[0]
            data=json.loads((home/path).read_text())
            data['discoveryContext']['chain_completeness_verified']=True
            invalid_path=folder/'tampered.json'; invalid_path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'completeness'):
                load_snapshot(folder/'db',invalid_path)
            self.assertEqual((folder/'db/latest.json').read_bytes(),publication)

    def test_status_reads_while_writer_lock_is_held_without_mutating_store(self):
        from analytics.workflow import locked
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); home=folder/'cp'; source=FixtureSource()
            source.fail='discover'
            with self.assertRaises(RuntimeError):
                start(home,folder/'db',CONFIG,source)
            before=(home/'checkpoints.sqlite3').read_bytes()
            with locked(home):
                child=subprocess.run([sys.executable,'-m','analytics.ingestion','--home',str(home),'status'],
                    capture_output=True,text=True,timeout=10)
            self.assertEqual(child.returncode,0,child.stderr)
            output=json.loads(child.stdout)
            self.assertEqual(output[0]['status'],'pending')
            self.assertFalse(output[0]['windows'][0]['work_complete'])
            self.assertEqual((home/'checkpoints.sqlite3').read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'not found'):
                status(folder/'missing')
            self.assertFalse((folder/'missing').exists())

    def test_rpc_endpoint_errors_are_sanitized_and_origin_excludes_secrets(self):
        for endpoint in ['https://rpc.example:FAKE_SECRET/path', 'https://user:FAKE_SECRET@rpc.example', 'https://[FAKE_SECRET']:
            with patch.dict(os.environ, {'TEMPO_RPC_URL':endpoint}):
                with self.assertRaises(ValueError) as error:
                    NodeSource()
                self.assertNotIn('FAKE_SECRET',str(error.exception))
        with patch.dict(os.environ, {'TEMPO_RPC_URL':'https://rpc.example:443/private?token=FAKE_SECRET'}):
            source=NodeSource()
            self.assertEqual(source.origin,'https://rpc.example')
        # Calls retain their configured endpoint even if the ambient env changes.
        with patch.dict(os.environ, {'TEMPO_RPC_URL':'https://other.example'}), patch('analytics.ingestion.subprocess.run') as run:
            run.return_value.returncode=0
            run.return_value.stdout='{}'
            source.call('anchor',config=CONFIG)
            self.assertEqual(run.call_args.kwargs['env']['TEMPO_RPC_URL'],source.endpoint)

    def test_config_bounds(self):
        for change in [{'toBlock':100000}, {'windowBlocks':0}, {'batchSize':101}, {'tokens':[]}, {'fromBlock':True}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_config({**CONFIG, **change})
