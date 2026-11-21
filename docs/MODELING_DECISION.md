# Modeling framework comparison

Decision confirmed by user on 2026-11-18: SQLMesh with DuckDB. AI-assisted development, interest in learning SQLMesh and frequent historical label backfills outweigh dbt familiarity. Earlier dbt-leaning advice is superseded. SQLMesh 0.236.4 and DuckDB 1.5.6 are now installed and pinned; the first synthetic label/backfill acceptance test passes.

Cloud-backend follow-up (2026-11-20): MotherDuck Lite is selected for v1 while retaining SQLMesh and DuckDB dialect. Local DuckDB is still the implemented pilot. [Backend decision](BACKEND_DECISION.md) owns benchmark and portability requirements; DuckLake is a future option.

## Decision

Use native SQLMesh models with DuckDB initially. SQLMesh owns model dependencies, plans, model versions, interval execution and audits. Project-specific code owns ingestion, evidence normalization, label resolution and determining which history a source-data correction affects. Do not build a custom modeling orchestrator; retries, dependency invalidation, interval state, concurrent execution and reproducible publication would become our long-term maintenance responsibility. AI assistance helps implement these systems but does not remove their correctness obligations. DuckDB remains an initial execution engine, not a permanent warehouse commitment.

DuckDB executes SQL; dbt or SQLMesh manages models, dependencies and build behavior. The flexible attribute/relationship schema, immutable source evidence and metric contracts are independent of that choice. No framework automatically solves temporal identity, missing historical coverage, money precision or cohort semantics.

## Tradeoffs

| Concern | dbt Core + dbt-duckdb | SQLMesh + DuckDB |
| --- | --- | --- |
| Handoff/ecosystem | Assessment: broader conventional analytics workflow and familiarity; model SQL, refs, YAML tests and adapters travel well. DuckDB adapter itself is community maintained. | More specialized workflow; contributors need to understand plans, snapshots, physical/virtual models and state. |
| Incremental processing | Supports append, delete+insert, merge and microbatch table models; microbatch supplies bounded time-window rebuilds. Correct lookback and downstream restatement still need design. | Integrated interval state, plan/apply and model-change handling; useful for repeated corrections/backfills. Still requires correct time dependencies and source-change handling. |
| Environments / deployment | Use targets/schemas, artifacts, state selection/defer and CI conventions; assemble the deployment workflow. | Built-in plans and virtual environments can reuse unchanged physical models and show affected intervals before applying. |
| Operational footprint | A runner, persistent model data, stored artifacts and a scheduler. No SQLMesh-specific state service. | DuckDB state is fine locally; shared production state requires a robust database such as PostgreSQL, plus backup/migration discipline. |
| Portability | Broad adapter path, but dialect-specific SQL, macros, UDFs and external materializations must be adapted/tested on a new engine. | Multiple engines and SQL-aware analysis; SQLMesh model metadata/state/macros create framework migration work. It can run dbt projects, with compatibility changes. |
| R2/Parquet | External Parquet models supported, but incremental external materializations are not supported by dbt-duckdb. Build incremental database tables, then export snapshots. | Use DuckDB for file reads and supported table materialization. Do not assume plain Parquet objects behave like transactional tables. |
| Governance / longevity | dbt-duckdb is Apache-2.0; its maintenance and compatibility are distinct from the wider dbt platform. Current v2 integration has a different driver path. | Current SQLMesh repository is Apache-2.0 and identifies the project as Linux Foundation hosted; this reduces the basis for treating it as merely a single-vendor experiment, but guarantees neither staffing nor future compatibility. |

## Concrete project example

Suppose a corrected operator mapping reassigns a service for the past 90 days. Both tools can rebuild affected operator-day totals. SQLMesh provides an integrated plan and restatement workflow; dbt can use selected models and bounded microbatch rebuilds. Neither can infer the intended economic/temporal meaning of the correction. A first-observed date correction may affect all later cohorts and growth metrics, beyond the 90-day source interval. Tests and explicit downstream rebuild rules are mandatory in both.

## Version and migration caveats

- The Python adapter currently documents merge (DuckDB >=1.4), microbatch (dbt Core >=1.9), and no incremental external-file materialization. Pin and exercise the actual version combination before implementation, not only broad minimum versions.
- Current dbt v2 docs describe built-in DuckDB support. They also document extension-driver requirements, incomplete parity with the v1 adapter and static-analysis gaps for local file readers. Do not assume installing/upgrading to v2 preserves Python adapter plugins, R2/file access or materializations unchanged.
- SQLMesh can load dbt projects, but its documentation explicitly requires changes to common incremental logic. This is a possible exit path, not a free drop-in switch. Native SQLMesh models do not automatically become a dbt project in reverse.
- Keep money/date/identity SQL as portable as practical; isolate engine-specific functions, storage paths and framework macros. Preserve raw data, schema versions, SQL, metric definitions and synthetic correctness fixtures outside framework runtime state. Use one production model owner/writer.

## First implementation acceptance cases

Use a small synthetic dataset to validate the selected SQLMesh stack: initial build, late arriving transfer, corrected operator mapping, affected-period rebuild, retry idempotency, as-of join, rolling/cohort history dependency and Parquet export/reload. Test source-data-only label changes as well as SQL code changes: a new label row does not automatically imply SQLMesh has detected all affected historical intervals. The label change must explicitly trigger the appropriate restatement. The first acceptance run now passes for source-only historical category changes, temporal joins, daily/rolling rebuilds, exact amounts, retry idempotency and publication failure recovery. Late source transfers, operator corrections, cohort dependencies and Parquet export/reload remain future acceptance cases. See analytics/README.md.

## Sources

- [dbt-duckdb README](https://github.com/duckdb/dbt-duckdb): adapter capabilities, licensing, exact incremental/external limitations.
- [dbt DuckDB setup](https://docs.getdbt.com/docs/core/connect-data-platform/duckdb-setup): community adapter support status.
- [dbt microbatch](https://docs.getdbt.com/docs/build/incremental-microbatch): time-window batching and backfills; filter upstream event-time inputs correctly.
- [dbt v2 DuckDB](https://docs.getdbt.com/docs/local/connect-data-platform/duckdb-setup): built-in driver, extensions and compatibility limitations.
- [SQLMesh plans](https://sqlmesh.readthedocs.io/en/latest/concepts/plans/): model changes, snapshots and affected intervals.
- [SQLMesh dbt integration](https://sqlmesh.readthedocs.io/en/stable/integrations/dbt/): compatibility and incremental changes.
- [SQLMesh repository](https://github.com/SQLMesh/sqlmesh): current Linux Foundation affiliation and Apache-2.0 license.
- [SQLMesh DuckDB](https://sqlmesh.readthedocs.io/en/latest/integrations/engines/duckdb/): local versus shared production state.
