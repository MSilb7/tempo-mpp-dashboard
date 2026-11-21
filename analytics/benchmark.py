"""Opt-in synthetic benchmark harness; planning is offline and is the default."""
import argparse
import hashlib
import json
import threading
import time
from datetime import date, timedelta, timezone, datetime
from pathlib import Path
from unittest.mock import patch

import psutil

from analytics.backend import Backend, assert_fresh
from analytics.schema import create_raw
from analytics.workflow import connect, drain, encoded, enqueue, locked, mesh, publish


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def plan(days=30, services=10, payments_per_day=100):
    if any(type(n) is not int for n in (days, services, payments_per_day)):
        raise ValueError('Benchmark dimensions must be integers')
    if not 2 <= days <= 3650 or not 2 <= services <= payments_per_day or days*payments_per_day > 1000000:
        raise ValueError('Use 2–3650 days, 2–payments_per_day services and at most 1,000,000 payments')
    return dict(schema_version=1, synthetic=True, days=days, services=services,
        payments_per_day=payments_per_day, payment_count=days*payments_per_day,
        history_start='2026-01-01', scenarios=['incremental_refresh','historical_service_relabel','broad_taxonomy_correction'],
        models=['enriched_transfers','daily_metrics','rolling_7d'],
        not_implemented=['weekly','monthly','cohort models'],
        cost_policy='Target $0/month MotherDuck; no overages or upgrades authorized. Measure CU consumption separately from elapsed time.',
        remote_prerequisites=['authorized usage and verified free-tier cutoff','dedicated empty database',
            'serialized runner and durable home','compatible SQLMesh/DuckDB/MotherDuck versions'])


def fingerprint(db):
    digest = hashlib.sha256()
    for row in db.execute('SELECT * FROM raw.transfers ORDER BY transfer_id').fetchall():
        digest.update(json.dumps(row, default=encoded).encode())
    return digest.hexdigest()


def seed(db, first, last, per_day, services):
    origin = date(2026,1,1)
    for index in range(first,last):
        day = origin+timedelta(days=index)
        db.execute('INSERT INTO raw.calendar VALUES (?)', [day])
        # Exact deterministic values; no real payer, service, token or receipt data.
        db.executemany('INSERT INTO raw.transfers (transfer_id,event_date,service_id,payer,token,amount_atomic,synthetic) VALUES (?,?,?,?,?,?,true)',
            [(f'benchmark-{index}-{j}',day,f'benchmark-service-{j%services}',
              f'benchmark-payer-{j%max(1,per_day//2)}','benchmark-token',str(j+1)) for j in range(per_day)])


def build(home, incremental=False):
    with connect(home) as db:
        first,last = db.execute('SELECT min(event_date),max(event_date) FROM raw.calendar').fetchone()
    execution=(last+timedelta(days=1)).isoformat()
    with mesh(home) as ctx:
        if incremental:
            result = ctx.run('prod', execution_time=execution, ignore_cron=True)
            ensure(result.is_success or result.is_nothing_to_do, 'Incremental SQLMesh run failed')
        else:
            ctx.plan('prod',execution_time=execution,no_prompts=True,auto_apply=True)
    return publish(home)


def interval_check(home):
    with connect(home) as db:
        first,last=db.execute('SELECT min(event_date),max(event_date) FROM raw.calendar').fetchone()
    begin=int(datetime.combine(first,datetime.min.time(),timezone.utc).timestamp()*1000)
    end=int(datetime.combine(last+timedelta(days=1),datetime.min.time(),timezone.utc).timestamp()*1000)
    with mesh(home) as ctx:
        snapshots=ctx.state_sync.get_snapshots([s.snapshot_id for s in ctx.snapshots.values()])
        checked=[]
        for s in snapshots.values():
            if s.model.kind.is_incremental_by_time_range:
                cursor=begin
                for lo,hi in sorted(s.intervals):
                    if lo <= cursor:
                        cursor=max(cursor,hi)
                if cursor < end:
                    raise ValueError('SQLMesh intervals do not cover the published history')
                checked.append(s.name)
        if len(checked)!=2:
            raise ValueError('Expected two incremental models for interval validation')
        return checked


def measure(name, action, home, runs, expected_failure=False):
    process=psutil.Process()
    stopped=threading.Event()
    peak=dict(rss_bytes=None,local_storage_bytes=None)
    unavailable_resources=set()
    def sample():
        while not stopped.is_set():
            try:
                try:
                    processes=[process]+process.children(recursive=True)
                except (psutil.Error,OSError):
                    processes=[process]
                    unavailable_resources.add('child process RSS unavailable; sampled current process only')
                peak['rss_bytes']=max(peak['rss_bytes'] or 0,sum(p.memory_info().rss for p in processes if p.is_running()))
            except (psutil.Error,OSError):
                unavailable_resources.add('RSS sampling unavailable')
            try:
                peak['local_storage_bytes']=max(peak['local_storage_bytes'] or 0,sum(p.stat().st_size for p in home.rglob('*') if p.is_file()))
            except OSError:
                unavailable_resources.add('some local storage samples unavailable')
            stopped.wait(.1)
    thread=threading.Thread(target=sample,daemon=True); thread.start()
    cpu=process.cpu_times(); started=time.perf_counter(); outcome='passed'
    try:
        result=action()
        if expected_failure:
            raise AssertionError('Expected injected publication failure')
        return result
    except RuntimeError as error:
        if not expected_failure or str(error)!='benchmark injected publication failure':
            outcome='failed'
            raise
        outcome='injected_failure_observed'
    except BaseException:
        outcome='failed'
        raise
    finally:
        stopped.set(); thread.join()
        final_cpu=process.cpu_times()
        runs.append(dict(scenario=name,outcome=outcome,wall_seconds=time.perf_counter()-started,
            runner_cpu_seconds=(final_cpu.user+final_cpu.system)-(cpu.user+cpu.system),
            sampled_peak_runner_tree_rss_bytes=peak['rss_bytes'],sampled_peak_local_storage_bytes=peak['local_storage_bytes'],
            resource_scope='Local process CPU; sampled process tree RSS and home storage. Excludes remote warehouse resources.',
            resource_limitations=sorted(unavailable_resources),
            scanned_bytes=None,rewritten_bytes=None,pulse_cu_hours=None,billed_cost_usd=None,
            unavailable='Warehouse scan/rewrite and billing telemetry not collected; null is unknown, not zero.'))


def run(home, days=30, services=10, payments_per_day=100, allow_remote=False):
    report=plan(days,services,payments_per_day)
    backend=Backend.from_env(home)
    if backend.kind!='duckdb' and not allow_remote:
        raise ValueError('Remote benchmarks require separate authorization and --allow-remote')
    backend.require_execution()
    report.update(backend=backend.kind, runs=[], validation={}, production_sizing=False)
    home=Path(home).resolve()
    # A benchmark is exclusive, fresh and synthetic; it never resets a warehouse.
    with locked(home):
        assert_fresh(home)
        try:
            with connect(home) as db:
                create_raw(db)
                seed(db,0,days-1,payments_per_day,services)
            measure('baseline_build',lambda:build(home),home,report['runs'])
            with connect(home) as db:
                before_rows=db.execute('SELECT count(*) FROM raw.transfers').fetchone()[0]
                old_facts=db.execute('SELECT * FROM raw.transfers ORDER BY transfer_id').fetchall()
            last=date(2026,1,1)+timedelta(days=days-1)
            def incremental():
                with connect(home) as db:
                    db.execute('BEGIN')
                    seed(db,days-1,days,payments_per_day,services)
                    db.execute('COMMIT')
                return build(home,incremental=True)
            measure('incremental_refresh',incremental,home,report['runs'])
            incremental_publication=(home/'latest.json').read_bytes()
            measure('incremental_refresh_retry',lambda:build(home,incremental=True),home,report['runs'])
            ensure((home/'latest.json').read_bytes()==incremental_publication, 'Incremental retry changed publication')
            with connect(home) as db:
                ensure(db.execute('SELECT count(*) FROM raw.transfers').fetchone()[0]==before_rows+payments_per_day, 'Incremental row count mismatch')
                ensure(db.execute('SELECT * FROM raw.transfers WHERE event_date<? ORDER BY transfer_id',[last]).fetchall()==old_facts, 'Incremental refresh changed historical facts')
                facts=fingerprint(db)
            label=dict(assertion_id='benchmark-label-0',service_id='benchmark-service-0',category='web_search',
                valid_from='2026-01-01',valid_to=(last+timedelta(days=1)).isoformat(),
                recorded_at=datetime.now(timezone.utc).isoformat(),evidence_level='model-inferred',source='synthetic-benchmark')
            def relabel():
                enqueue(home,label)
                return drain(home)
            measure('historical_service_relabel',relabel,home,report['runs'])
            prior=(home/'latest.json').read_bytes()
            measure('duplicate_label_retry',relabel,home,report['runs'])
            ensure((home/'latest.json').read_bytes()==prior, 'Previous publication changed unexpectedly')
            # Submit the approved batch once; one union restatement, not N rebuilds.
            for service in range(1,services):
                enqueue(home,{**label,'assertion_id':f'benchmark-label-{service}',
                    'service_id':f'benchmark-service-{service}','category':'enrichment'})
            with patch('analytics.workflow.publish',side_effect=RuntimeError('benchmark injected publication failure')):
                measure('broad_taxonomy_failed_publication',lambda:drain(home),home,report['runs'],expected_failure=True)
            ensure((home/'latest.json').read_bytes()==prior, 'Previous publication changed unexpectedly')
            measure('broad_taxonomy_resume',lambda:drain(home),home,report['runs'])
            with connect(home) as db:
                ensure(fingerprint(db)==facts, 'Relabel changed immutable raw facts')
                ensure(db.execute("SELECT count(*) FROM raw.label_changes WHERE status='pending'").fetchone()[0]==0, "Pending labels remain")
            report['validation']=dict(raw_facts_invariant=True,duplicate_retry_idempotent=True,
                incremental_refresh_retry_idempotent=True,
                previous_publication_preserved_on_failure=True,publication_audits_passed=True,
                incremental_sqlmesh_intervals=interval_check(home),
                hard_process_restart='Covered by offline integration tests; not executed by this harness',
                overlapping_cloud_triggers='Not validated; requires external serialization acceptance')
            report['affected_interval']=dict(start='2026-01-01',end_exclusive=(last+timedelta(days=1)).isoformat())
            report['status']='passed'
        except BaseException:
            report['status']='failed'
            raise
        finally:
            # No credentials, connection strings, identifiers from live data or raw errors.
            temp=home/'benchmark-report.json.tmp'
            temp.write_text(json.dumps(report,indent=2)+'\n')
            temp.replace(home/'benchmark-report.json')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,default=Path('.local/benchmark'))
    parser.add_argument('--days',type=int,default=30)
    parser.add_argument('--services',type=int,default=10)
    parser.add_argument('--payments-per-day',type=int,default=100)
    parser.add_argument('--execute',action='store_true',help='Run on a fresh isolated synthetic database; default only prints plan')
    parser.add_argument('--allow-remote',action='store_true',help='Requires separate usage authorization; never needed for offline smoke tests')
    args=parser.parse_args()
    dimensions=dict(days=args.days,services=args.services,payments_per_day=args.payments_per_day)
    if args.execute:
        result=run(args.home,allow_remote=args.allow_remote,**dimensions)
        print(f"Benchmark {result['status']}; report: {args.home/'benchmark-report.json'}")
    else:
        print(json.dumps(plan(**dimensions),indent=2))


if __name__=='__main__':
    main()
