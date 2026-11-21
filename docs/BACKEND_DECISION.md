# V1 analytical backend: MotherDuck Lite

Confirmed user decision, 2026-11-20: choose **MotherDuck Lite** for v1, retain SQLMesh and the DuckDB dialect, and prioritize simplicity. DuckLake with R2/PostgreSQL is a future migration option, not the v1 implementation target. This supersedes the earlier open cloud-backend comparison; local DuckDB remains the implemented development/test environment.

The proposed execution path is Cloudflare orchestration → portable SQLMesh Linux container → MotherDuck Lite → audited, versioned publications → dashboard. The entire pipeline must run without a laptop or active Codex session. Cloudflare remains preferred for orchestration, runner and serving; exact products are not yet selected. A small managed PostgreSQL SQLMesh state connection is recommended for validation, not a chosen provider. No account setup, provisioning, MotherDuck benchmark or version upgrade has occurred.

SQLMesh documents a [MotherDuck integration](https://sqlmesh.readthedocs.io/en/stable/integrations/engines/motherduck/) using the DuckDB dialect. Verify compatibility with our pinned versions and validate the [state connection](https://sqlmesh.readthedocs.io/en/stable/guides/configuration/#state-connection) before implementing production execution. A backend switch does not supply distributed locks or automatic source-label impact detection.

## Acceptance benchmarks before production sizing

| Scenario | Scope |
| --- | --- |
| Normal incremental refresh | Representative new ingestion and downstream refresh, including repeat delivery. |
| Historical service relabel | One service across representative history, including downstream window tails. |
| Broad taxonomy correction | Multiple services and affected daily/weekly/monthly, rolling or cohort models as implemented. Record unsupported models rather than claiming coverage. |

For each run record dataset size, history span, affected intervals, scanned/rewritten data where observable, wall time, billed Pulse CU consumption/cost where available, peak runner CPU/memory/disk and validation outcomes. Record unavailable observability explicitly. Pulse CU-hours measure resource consumption, not elapsed job hours. Tiny synthetic acceptance fixtures cannot establish production sizing; benchmark representative scale with documented coverage and selection bias.

Require raw-fact invariance, per-token conservation, correct category/distinct/window results, idempotent retry, interruption/restart recovery, overlapping-trigger serialization, SQLMesh interval consistency and preservation of the last validated publication on failure. Compare results against the local baseline. State intervals must not advance beyond durable warehouse results. No MotherDuck benchmark results exist yet; account access, permitted data and spending limits remain prerequisites for any paid execution.

## Modeling and backfill policy

Keep immutable payment facts separate from sourced, time-versioned labels. Detail views may join labels directly; materialized aggregates require explicit affected-interval restatement and propagation through downstream window dependencies. Batch approved changes whose affected intervals overlap to avoid redundant rebuilding. Service-level aggregates can accelerate additive metrics, but distinct-payer and cohort metrics may need underlying facts; never silently approximate them.

Retain the existing source-only label workflow and audit/publication gate. The current conservative full-span restatement is the correctness baseline, not a claim of optimized MotherDuck performance.

## Portability contract

- Retain raw evidence and portable exports in R2; keep label and provenance history independently exportable. These cloud paths remain to be implemented.
- Keep predominantly shared DuckDB SQL. Centralize connection, catalog and storage handling behind a small adapter instead of adding scattered `warehouse.duckdb` opens.
- Use a portable Linux container and separate analytical connection from SQLMesh state configuration. Re-test transaction, permissions and recovery behavior on the selected backend.
- Serve validated publication artifacts; the dashboard must not depend on provider-specific warehouse internals.

A later DuckLake migration is **load facts/labels → rebuild → compare metrics → switch publication**. It is not promised to be configuration-only: SQLMesh environments/state, compatible versions, permissions, transaction semantics and recovery must be retested. Keep the last good publication available until replacement passes audits.

## Dated cost reference and upgrade boundary

Official [pricing](https://motherduck.com/docs/about-motherduck/billing/pricing/) checked 2026-11-20: Lite has a $0 platform fee, 10 GB storage and 10 Pulse CU-hours/month included. AWS US additional storage is $0.04/GB-month and Pulse is $0.60/CU-hour. Storage billing includes historical/retained bytes and uses average storage. Larger Duckling compute requires Business ($250/month plus usage).

Illustration, not a forecast: 100 GB average total billable storage and 30 Pulse CU-hours yield `(100−10)×$0.04 + (30−10)×$0.60 = $15.60` in Lite warehouse charges, assuming no Flights sharing of the compute allocation. Runner, state database, R2 and other services are excluded. Recheck region, retention, allowances and rates before spending.

The confirmed operating target is **$0/month MotherDuck** and low overall side-project cost. The illustration above is not an approved budget. Prefer no paid billing; verify free-allowance cutoff/overage behavior before unattended use. Start with daily refresh, bounded history expansion and batched labels/backfills; serve precomputed publications and pause or slow refresh before overages. No dollar cap or paid upgrade is authorized; propose any small subscriptions before buying them.

Before purchasing a larger MotherDuck plan, compare a small cloud VM running ordinary DuckDB + SQLMesh on persistent disk. Include measured backfill time, disk needs, backups, restore tests, scheduling and operating effort. DuckLake is a later fallback, not the immediate alternative. Do not silently upgrade.

## Implementation checkpoint

The adapter, container definition and offline benchmark harness now exist; see [RUNNER.md](RUNNER.md). Local tests validate target isolation, explicit remote guards, date bounds beyond the demo, relabel/retry/recovery and persisted SQLMesh intervals. No actual MotherDuck/PostgreSQL connection or paid benchmark has run. Docker is unavailable locally; image build and network-disabled smoke passed GitHub Actions on 2026-11-21. Representative remote sizing, free-tier controls and cloud single-writer/recovery acceptance remain outstanding.
