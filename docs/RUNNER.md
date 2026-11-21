# Backend adapter, portable runner and benchmarks

Implemented on 2026-11-20; reviewed on 2026-11-21. **Container build and network-disabled smoke passed CI; MotherDuck connectivity remains unverified**. No MotherDuck/PostgreSQL connection, provisioning or paid benchmark has been performed. [Backend decision](BACKEND_DECISION.md) owns product, cost and migration requirements.

## Local DuckDB remains the default

Existing [onboarding commands](START_HERE.md) work unchanged. `analytics/backend.py` owns direct connections, catalog-scoped metadata checks and SQLMesh connection settings. `backend.json` binds a home to its backend/database/state target and contains no passwords or tokens. Reusing a home for a different target fails; use a new home, never change the binding by hand. Legacy local homes receive a binding without moving their data.

Label restatement and publication date bounds now derive from the calendar rather than the original ten-day demo. Model SQL, source/label semantics and audited publication remain shared between backends. `init-demo` still creates only the fixed synthetic fixture and refuses an initialized database.

## MotherDuck connection configuration — not a provisioning command

The supported interface is the Python workflow CLI, not a separately invoked SQLMesh CLI config. Supply these through runtime environment or a secret manager, never a committed file or image build argument:

| Variable | Purpose |
| --- | --- |
| `TEMPO_BACKEND=motherduck` | Select the adapter; otherwise default is `duckdb`. |
| `TEMPO_MOTHERDUCK_DATABASE` | Dedicated database identifier, lowercase letters/digits/underscores beginning with a letter. |
| `motherduck_token` | SDK runtime authentication; never put the token in connection strings. |
| `TEMPO_ENABLE_REMOTE=1` | Explicitly permit network/warehouse execution after usage is authorized. Default fails before connecting. |
| `TEMPO_REMOTE_SINGLE_WRITER=1` | Acknowledge externally serialized execution. This is a prerequisite assertion, **not** an implemented distributed lock. |
| `TEMPO_STATE_MODE=local` or `postgres` | Explicit SQLMesh state choice; never silently store state in MotherDuck. |

`local` state uses `sqlmesh-state.duckdb` in the home, suitable only for a serialized pilot on durable storage. `postgres` uses `TEMPO_STATE_HOST`, `TEMPO_STATE_PORT` (default 5432), `TEMPO_STATE_DATABASE`, `TEMPO_STATE_USER`, `TEMPO_STATE_PASSWORD` and TLS `verify-full`. Supply trusted CA material through the PostgreSQL driver's standard runtime configuration. Install `analytics/requirements-cloud.txt` for its optional driver. Use a dedicated state database per analytical target; a local home binding cannot protect a shared state database from another runner. No managed PostgreSQL provider is selected or created.

Direct and SQLMesh connections select the same MotherDuck database with single-database attachment and UTC sessions. The pinned SQLMesh MotherDuck connection ignores generic connector settings, so a small subclass supplies UTC explicitly. Configuration and driver-call tests are mocked for MotherDuck; a real compatibility test remains required before unattended use.

The opt-in switches do not enforce a free allowance, spending cap or subscription tier. Target $0 MotherDuck spend, verify account cutoff/overage behavior first, and get approval before paid use or upgrades. No credentials or these opt-ins are supplied in CI.

## Portable Linux container

```sh
docker build --platform linux/amd64 -t tempo-analytics:local .
docker run --rm --network none tempo-analytics:local unittest discover -s analytics/tests -v
docker run --rm --network none tempo-analytics:local analytics.benchmark \
  --home /data/smoke --days 3 --services 2 --payments-per-day 4 --execute
```

The image combines Python 3.13, Node 22 and pinned dependencies. It runs as non-root UID 10001. The `.dockerignore` uses an allowlist, excluding `.local`, Git metadata, credentials, caches, databases and logs from the build context. No secret is a build argument. Public dependency/image downloads are needed during build; smoke execution is network-disabled.

`/data` contains writable state/publications; `TEMPO_ANALYTICS_DIR=/data/analytics` is the workflow default. Use a persistent, correctly owned volume for retained runs. For example, mount a local directory writable by UID 10001 at `/data`, then run `analytics.cli init-demo`. A disposable smoke volume is not a backup strategy. The image's entrypoint is `python -m`, so `analytics.cli`, `analytics.ingestion` and `analytics.benchmark` are module arguments.

Docker/Podman are unavailable on this workstation. Image build and network-disabled test/benchmark execution passed [CI run 44869402477](https://github.com/MSilb7/tempo-mpp-dashboard/actions/runs/44869402477); [PR #3](https://github.com/MSilb7/tempo-mpp-dashboard/pull/3) tracks the reviewed changes. Cloud scheduling, shared checkpoint persistence, R2 upload, global writer coordination, publication-pointer updates and state backups are not provisioned by this Dockerfile. Preserve last-good publication and state/data consistency when implementing those pieces.

## Benchmark harness

Planning is the default and performs no connection:

```sh
.local/venv/bin/python -m analytics.benchmark --days 30 --services 10 --payments-per-day 100
```

Run a small **local-only synthetic smoke test**, using a fresh home:

```sh
TEMPO_BACKEND=duckdb .local/venv/bin/python -m analytics.benchmark \
  --home .local/benchmark-smoke --days 3 --services 2 --payments-per-day 4 --execute
```

The harness refuses to reset existing data. It builds a baseline, adds the final day using the SQLMesh incremental runner, retries that refresh without restatement, relabels one service, retries that label, batches the remaining service labels, injects a publication failure and resumes. It checks historical fact invariance, exact metrics via publication audits, unchanged prior publication on failure, idempotency and persisted incremental SQLMesh interval coverage. Broad-backfill failure and retry are timed separately; do not report their combined compute as a single clean backfill. Generation uses deterministic synthetic facts and `executemany`, not a live-ingestion throughput test.

`benchmark-report.json` records dimensions/history/affected intervals, wall time, runner CPU, sampled peak RSS/local storage, unavailable resource observations and validation outcomes. Scanned/rewritten bytes, Pulse CU-hours and billed cost remain **null (unavailable)** until provider telemetry is integrated. Runner wall time is never converted into billed CU consumption. Sampling may miss transient peaks; remote warehouse resources are excluded. Reports remain ignored local artifacts.

Remote execution additionally requires `--allow-remote` plus all adapter opt-ins. Do not invoke it until authorized and account free-tier behavior is verified; it can issue many billable queries. No remote benchmark was run for this change. Representative-scale sizing, hard process restart on MotherDuck and overlapping cloud-trigger serialization still need acceptance; local integration tests cover the existing process-crash/retry path. Weekly/monthly/cohort models are explicitly marked unimplemented rather than benchmarked.

## Next acceptance steps

The image smoke passed CI. Next validate compatible MotherDuck versions, free-tier cutoff and serialized runner/storage design before any authorized connectivity test. Default deployment intent is daily refresh, bounded history and batched backfills, serving precomputed publications. Pause or slow updates before overages. Before purchasing a larger MotherDuck plan, compare a small persistent-disk VM running SQLMesh + ordinary DuckDB, including measured backfill speed, backups, restore testing and operating work. DuckLake is a later fallback.
