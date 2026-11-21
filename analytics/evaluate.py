"""Deterministic offline system acceptance eval; no remote execution option."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch

from analytics.ingestion import start
from analytics.workflow import connect, ingest_label, resume
from analytics.snapshots import ROOT

CONFIG = dict(chainId='4217', fromBlock=10, toBlock=10,
              tokens=['0x20c0'+'0'*35+'1'], windowBlocks=1, batchSize=1)


class DiscoveryPaymentRequired(RuntimeError):
    """The fixture observed the production parser's specific HTTP 402 rejection."""


class SyntheticSource:
    synthetic = True
    origin = 'https://rpc.synthetic.example'

    def __init__(self):
        self.reject_discovery = False

    def call(self, operation, config=None, selection=None):
        child = subprocess.run(['node', str(ROOT/'analytics/tests/eval_source.mjs')],
            input=json.dumps(dict(operation=operation, config=config, selection=selection,
                                  rejectDiscovery=self.reject_discovery)),
            capture_output=True, text=True, timeout=30)
        if child.returncode:
            raise RuntimeError('Synthetic acquisition rejected')
        result = json.loads(child.stdout)
        if result.get('error') == {'code':'discovery_http_402'}:
            raise DiscoveryPaymentRequired('Synthetic discovery HTTP 402')
        return result


def run():
    if os.environ.get('TEMPO_BACKEND', 'duckdb') != 'duckdb':
        raise ValueError('System eval supports only offline local DuckDB')
    report = dict(schema_version=1, suite='offline-system-v1', synthetic=True,
                  status='running', checks=[], limitations=[
                      'Transport responses are synthetic; no live endpoint availability or schema drift test.',
                      'Publishes local audited JSON; cloud delivery and dashboard rendering are not exercised.',
                      'Timing is diagnostic only, not a production performance or billing score.'])
    def check(name, condition):
        report['checks'].append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise ValueError(name)
    began = time.monotonic()
    stage = 'acquire_parse_model_publish'
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cp = root/'checkpoints'; warehouse = root/'warehouse'
            source = SyntheticSource()
            result = start(cp, warehouse, CONFIG, source)
            output = lambda: json.loads((warehouse/'latest.json').read_text())
            out = output()
            check(stage, result['status']=='complete')
            check('golden_payment_count', sum(r['payment_count'] for r in out['daily'])==2)
            check('golden_exact_atomic_volume', sum(int(r['amount_atomic']) for r in out['daily'])==18014398509481986)
            check('unknown_category_preserved', all(r['category']=='unknown' for r in out['daily']))
            check('coverage_is_selection_only', not out['coverage']['complete_for_day'] and not out['coverage']['complete_for_block_range'])
            manifests = out['provenance']['snapshots']
            check('discovery_provenance_retained', len(manifests)==1 and all(
                m.get('discovery_context', {}).get('pages')==2 and
                m['discovery_context'].get('api_rows')==2 and
                m['discovery_context'].get('candidate_transactions')==1 and
                m['discovery_context'].get('chain_completeness_verified') is False
                for m in manifests))
            stage = 'repeat_and_overlap'
            prior = (warehouse/'latest.json').read_bytes()
            start(cp, warehouse, CONFIG, source)
            check('exact_rerun_publication_stable', (warehouse/'latest.json').read_bytes()==prior)
            start(cp, warehouse, {**CONFIG, 'observationKey':'overlap'}, source)
            check('overlap_metrics_stable', output()['daily']==out['daily'] and output()['rolling_7d']==out['rolling_7d'])
            stage = 'historical_label_failure_recovery'
            with connect(warehouse) as db:
                facts = db.execute('SELECT * FROM raw.transfers ORDER BY transfer_id').fetchall()
            label = dict(assertion_id='eval-label', service_id='tempo-4217-0x'+'ab'*10,
                category='web_search', valid_from='2023-11-14', valid_to='2023-11-15',
                recorded_at='2026-01-01T00:00:00Z', evidence_level='model-inferred', source='synthetic-eval')
            prior = (warehouse/'latest.json').read_bytes()
            failed = False
            with patch('analytics.workflow.publish', side_effect=RuntimeError('eval publication failure')), patch('analytics.snapshots.publish', side_effect=RuntimeError('eval publication failure')):
                try:
                    ingest_label(warehouse, label)
                except RuntimeError as error:
                    if str(error) != 'eval publication failure':
                        raise
                    failed = True
            check('injected_failure_observed', failed)
            check('last_good_publication_preserved', (warehouse/'latest.json').read_bytes()==prior)
            resume(warehouse)
            labeled = output()
            check('golden_historical_relabel', sum(int(r['amount_atomic']) for r in labeled['daily'] if r['category']=='web_search')==18014398509481986)
            with connect(warehouse) as db:
                check('raw_facts_unchanged', db.execute('SELECT * FROM raw.transfers ORDER BY transfer_id').fetchall()==facts)
            stage = 'gated_source_rejection'
            prior = (warehouse/'latest.json').read_bytes()
            source.reject_discovery = True
            rejected = False
            try:
                start(cp, warehouse, {**CONFIG, 'observationKey':'gated'}, source)
            except DiscoveryPaymentRequired:
                rejected = True
            check('http_402_fails_closed', rejected)
            check('source_failure_preserves_publication', (warehouse/'latest.json').read_bytes()==prior)
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', failed_stage=stage, error_type=type(error).__name__)
    report['wall_seconds'] = time.monotonic()-began
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Optional local JSON report; no acquired data or credentials')
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2)+'\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text)
    raise SystemExit(0 if report['status']=='passed' else 1)


if __name__ == '__main__':
    main()
