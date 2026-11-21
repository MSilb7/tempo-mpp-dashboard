import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from analytics.backend import Backend, connect, table_count
from analytics.config import make_config
from analytics.benchmark import plan, run

REMOTE = dict(TEMPO_BACKEND='motherduck', TEMPO_MOTHERDUCK_DATABASE='synthetic_benchmark',
              TEMPO_STATE_MODE='local')


class BackendTests(unittest.TestCase):
    def test_default_local_and_current_catalog_isolation(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{},clear=True):
            home=Path(folder)
            with connect(home) as db:
                db.execute("ATTACH ':memory:' AS unrelated")
                db.execute('CREATE SCHEMA unrelated.raw')
                db.execute('CREATE TABLE unrelated.raw.snapshots (id INTEGER)')
                self.assertEqual(table_count(db),0)
                db.execute('CREATE SCHEMA raw')
                db.execute('CREATE TABLE raw.transfers (id INTEGER)')
                self.assertEqual(table_count(db),1)
            self.assertEqual(Backend.from_env(home).kind,'duckdb')
            config=make_config(home)
            self.assertIsNone(config.gateways['local'].state_connection)

    def test_remote_configuration_is_offline_and_execution_requires_opt_in(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,REMOTE,clear=True):
            home=Path(folder)
            with patch('analytics.backend.duckdb.connect') as driver:
                cfg=make_config(home)
                connection=cfg.gateways['local'].connection
                self.assertEqual(connection.type_,'motherduck')
                self.assertEqual(connection._static_connection_kwargs['database'],'md:synthetic_benchmark?attach_mode=single')
                self.assertEqual(connection._static_connection_kwargs['config']['TimeZone'],'UTC')
                self.assertIsNone(connection.token)
                self.assertEqual(cfg.gateways['local'].state_connection.database,str(home/'sqlmesh-state.duckdb'))
                with self.assertRaisesRegex(ValueError,'Remote execution disabled'):
                    connect(home)
                driver.assert_not_called()
                self.assertFalse((home/'backend.json').exists())

    def test_remote_connect_uses_env_token_and_target_binding(self):
        env={**REMOTE,'TEMPO_ENABLE_REMOTE':'1','TEMPO_REMOTE_SINGLE_WRITER':'1','motherduck_token':'synthetic-secret'}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,env,clear=True):
            home=Path(folder)
            with patch('analytics.backend.duckdb.connect',return_value=MagicMock()) as driver:
                connect(home)
                driver.assert_called_once_with('md:synthetic_benchmark?attach_mode=single')
                self.assertNotIn('synthetic-secret',(home/'backend.json').read_text())
                os.environ['TEMPO_MOTHERDUCK_DATABASE']='different_database'
                with self.assertRaisesRegex(ValueError,'binding'):
                    connect(home)
                self.assertEqual(driver.call_count,1)
                os.environ['TEMPO_MOTHERDUCK_DATABASE']='synthetic_benchmark'
            with patch('analytics.backend.duckdb.connect',side_effect=RuntimeError('synthetic-secret')):
                with self.assertRaises(RuntimeError) as error:
                    connect(home)
                self.assertNotIn('synthetic-secret',str(error.exception))

    def test_postgres_state_separate_and_reject_injected_database_names(self):
        env={**REMOTE,'TEMPO_STATE_MODE':'postgres','TEMPO_STATE_HOST':'state.example',
             'TEMPO_STATE_DATABASE':'sqlmesh_state','TEMPO_STATE_USER':'runner','TEMPO_STATE_PASSWORD':'synthetic-secret'}
        # Configuration-only test: base local installs need no PostgreSQL driver.
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,env,clear=True), patch.dict('sys.modules', {'psycopg2':MagicMock()}):
            cfg=make_config(Path(folder))
            self.assertEqual(cfg.gateways['local'].state_connection.type_,'postgres')
            self.assertEqual(cfg.gateways['local'].state_connection.sslmode,'verify-full')
            os.environ['TEMPO_MOTHERDUCK_DATABASE']='database?motherduck_token=bad'
            with self.assertRaisesRegex(ValueError,'identifier'):
                Backend.from_env(folder)

    def test_benchmark_plan_no_connection_and_remote_execution_guard(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,REMOTE,clear=True), patch('analytics.backend.duckdb.connect') as driver:
            self.assertEqual(plan(16,2,4)['payment_count'],64)
            with self.assertRaisesRegex(ValueError,'Remote benchmarks'):
                run(Path(folder)/'bench',days=16,services=2,payments_per_day=4)
            driver.assert_not_called()

    def test_local_benchmark_beyond_demo_dates(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'TEMPO_BACKEND':'duckdb'}):
            report=run(Path(folder),days=16,services=2,payments_per_day=4)
            self.assertEqual(report['status'],'passed')
            self.assertTrue(report['validation']['raw_facts_invariant'])
            self.assertTrue(report['validation']['incremental_refresh_retry_idempotent'])
            self.assertEqual(len(report['validation']['incremental_sqlmesh_intervals']),2)
            self.assertTrue(all(r['pulse_cu_hours'] is None for r in report['runs']))
            self.assertIn('injected_failure_observed',[r['outcome'] for r in report['runs']])
            out=json.loads((Path(folder)/'latest.json').read_text())
            self.assertEqual(out['coverage']['through'],'2026-01-16')
            self.assertEqual(sum(r['payment_count'] for r in out['daily']),64)
            with self.assertRaisesRegex(ValueError,'exists'):
                run(Path(folder),days=16,services=2,payments_per_day=4)

    def test_failed_session_setup_closes_connection(self):
        env={**REMOTE,'TEMPO_ENABLE_REMOTE':'1','TEMPO_REMOTE_SINGLE_WRITER':'1','motherduck_token':'synthetic-secret'}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,env,clear=True):
            db=MagicMock()
            db.execute.side_effect=RuntimeError('synthetic-secret')
            with patch('analytics.backend.duckdb.connect',return_value=db):
                with self.assertRaisesRegex(RuntimeError,'MotherDuck connection failed'):
                    connect(Path(folder))
            db.close.assert_called_once()
