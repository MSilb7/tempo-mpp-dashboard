import json
import os
import unittest
from unittest.mock import patch

from analytics.evaluate import run, SyntheticSource
from analytics.snapshots import publish


class SystemEvalTests(unittest.TestCase):
    def test_full_offline_system_acceptance(self):
        with patch.dict(os.environ, {'TEMPO_BACKEND':'duckdb'}):
            report = run()
        self.assertEqual(report['status'], 'passed', report)
        self.assertGreaterEqual(len(report['checks']), 14)
        self.assertTrue(all(check['passed'] for check in report['checks']))

    def test_eval_rejects_wrong_published_total(self):
        def corrupt(home):
            result = publish(home)
            path = home/'latest.json'
            payload = json.loads(path.read_text())
            payload['daily'][0]['payment_count'] += 1
            path.write_text(json.dumps(payload))
            return result
        with patch.dict(os.environ, {'TEMPO_BACKEND':'duckdb'}), patch('analytics.snapshots.publish', side_effect=corrupt):
            report = run()
        self.assertEqual(report['status'], 'failed')
        self.assertIn({'name':'golden_payment_count', 'passed':False}, report['checks'])

    def test_remote_backend_rejected_before_execution(self):
        with patch.dict(os.environ, {'TEMPO_BACKEND':'motherduck'}), patch('analytics.evaluate.start') as start:
            with self.assertRaisesRegex(ValueError, 'offline local'):
                run()
            start.assert_not_called()

    def test_missing_provenance_fails_eval(self):
        def corrupt(home):
            result = publish(home)
            path = home/'latest.json'
            payload = json.loads(path.read_text())
            payload['provenance']['snapshots'] = []
            path.write_text(json.dumps(payload))
            return result
        with patch.dict(os.environ, {'TEMPO_BACKEND':'duckdb'}), patch('analytics.snapshots.publish', side_effect=corrupt):
            report = run()
        self.assertEqual(report['status'], 'failed')
        self.assertIn({'name':'discovery_provenance_retained', 'passed':False}, report['checks'])

    def test_unrelated_source_error_is_not_payment_rejection(self):
        original = SyntheticSource.call
        def fail(source, operation, **kwargs):
            if source.reject_discovery:
                raise RuntimeError('Synthetic acquisition rejected')
            return original(source, operation, **kwargs)
        with patch.dict(os.environ, {'TEMPO_BACKEND':'duckdb'}), patch.object(SyntheticSource, 'call', fail):
            report = run()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['failed_stage'], 'gated_source_rejection')
        self.assertNotIn({'name':'http_402_fails_closed', 'passed':True}, report['checks'])
