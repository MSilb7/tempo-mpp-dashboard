import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analytics.snapshots import load_snapshot, ROOT
from analytics.workflow import connect, ingest_label, resume


def snapshot(**options):
    result = subprocess.run(["node", str(ROOT / "analytics/tests/make_snapshot.mjs")],
        input=json.dumps(options), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def save(folder, data):
    path = folder / 'input.json'
    path.write_text(json.dumps(data))
    return path


class SnapshotTests(unittest.TestCase):
    def test_overlap_retry_new_observation_and_historical_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); home = folder / 'warehouse'
            first = snapshot(ids=[2])
            load_snapshot(home, save(folder, first))
            before = (home / 'latest.json').read_bytes()
            self.assertIsNone(load_snapshot(home, save(folder, first)))
            self.assertEqual(before, (home / 'latest.json').read_bytes())
            load_snapshot(home, save(folder, snapshot(ids=[1, 2])))  # earlier source date
            load_snapshot(home, save(folder, snapshot(ids=[2, 3])))  # later + overlapping
            out = json.loads((home / 'latest.json').read_text())
            self.assertEqual(sum(r['payment_count'] for r in out['daily']), 3)
            self.assertEqual(sum(int(r['amount_atomic']) for r in out['daily']), 600)
            self.assertFalse(out['coverage']['complete_for_day'])
            self.assertFalse(out['coverage']['complete_for_block_range'])
            self.assertEqual(len(out['transfer_evidence']), 3)
            self.assertTrue(all(r['unknown_interface_payment_count'] == r['payment_count'] for r in out['daily']))
            counts_before = out['daily']
            fresh = snapshot(ids=[2], acquiredAt='2026-02-02T00:00:00Z')
            load_snapshot(home, save(folder, fresh))
            after = json.loads((home / 'latest.json').read_text())
            self.assertEqual(after['daily'], counts_before)
            self.assertEqual(len(after['provenance']['snapshots']), 4)
            with connect(home) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM raw.transfers').fetchone()[0], 3)
                self.assertEqual(db.execute('SELECT count(*) FROM raw.transfer_observations').fetchone()[0], 6)
            # Existing label pipeline now works with imported fingerprints and dates.
            service = 'tempo-4217-' + first['transfers'][0]['attribution']['serverFingerprint']
            ingest_label(home, {'assertion_id':'snapshot-label', 'service_id':service, 'category':'web_search',
                'valid_from':'2026-01-02','valid_to':'2026-01-03','recorded_at':'2026-02-02T00:00:00Z',
                'evidence_level':'operator-reported','source':'synthetic assertion'})
            labeled = json.loads((home / 'latest.json').read_text())
            self.assertEqual(sum(int(r['amount_atomic']) for r in labeled['daily'] if r['category']=='web_search'), 200)

    def test_population_precision_interface_and_empty_selection(self):
        universe = [
            {'id':1,'day':1,'amount':'9007199254740993','client':True},
            {'id':2,'day':1,'memo':'absent'}, {'id':3,'day':1,'memo':'other'},
            {'id':4,'day':1,'amount':'0'}, {'id':5,'day':1,'movement':'mint'},
            {'id':6,'day':1,'failed':True}]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); home = folder/'warehouse'
            data = snapshot(ids=[1,2,3,4,5,6], universe=universe)
            load_snapshot(home, save(folder, data))
            out = json.loads((home/'latest.json').read_text())
            self.assertEqual(out['daily'][0]['amount_atomic'], '9007199254740993')
            self.assertEqual(out['daily'][0]['payment_count'], 1)
            self.assertEqual(out['daily'][0]['unresolved_client_fingerprint_count'], 1)
            self.assertEqual(len(out['transfer_evidence']), 5)
            self.assertEqual(out['provenance']['snapshots'][0]['coverage']['failedTransactions'], 1)
            with connect(home) as db:
                self.assertEqual(db.execute('SELECT originating_interface FROM tempo.enriched_transfers').fetchone()[0], 'unknown')
            # A valid selected receipt set with no MPP is not an ingestion error.
            empty_home = folder/'empty'
            load_snapshot(empty_home, save(folder, snapshot(ids=[2],universe=universe)))
            self.assertEqual(json.loads((empty_home/'latest.json').read_text())['daily'], [])

    def test_tamper_conflicts_overflow_and_mode_rejection_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); home = folder/'warehouse'
            original = snapshot(ids=[1])
            load_snapshot(home, save(folder, original))
            before = (home/'latest.json').read_bytes()
            tampered = copy.deepcopy(original); tampered['transfers'][0]['amountAtomic'] = '999'
            bad_coverage = copy.deepcopy(original); bad_coverage['coverage']['completeForBlockRange'] = True
            cases = [tampered, bad_coverage, snapshot(ids=[1], reorg=True),
                snapshot(ids=[1], synthetic=False),
                snapshot(ids=[9], universe=[{'id':9,'day':9,'amount':str(10**38)}])]
            for data in cases:
                with self.subTest(data=data['synthetic']), self.assertRaises(ValueError):
                    load_snapshot(home, save(folder, data))
                self.assertEqual((home/'latest.json').read_bytes(), before)
            with connect(home) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM raw.snapshots').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM raw.movements').fetchone()[0], 1)

    def test_import_publication_failure_is_resumable(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); home=folder/'warehouse'
            load_snapshot(home, save(folder, snapshot(ids=[1])))
            before=(home/'latest.json').read_bytes()
            with patch('analytics.snapshots.publish', side_effect=RuntimeError('injected')):
                with self.assertRaisesRegex(RuntimeError,'injected'):
                    load_snapshot(home, save(folder, snapshot(ids=[1,2])))
            self.assertEqual((home/'latest.json').read_bytes(),before)
            resume(home)
            out=json.loads((home/'latest.json').read_text())
            self.assertEqual(sum(r['payment_count'] for r in out['daily']),2)
            self.assertIsNone(resume(home))


if __name__ == '__main__':
    unittest.main()
