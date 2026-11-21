# SQLMesh + DuckDB label pilot

For the opt-in MotherDuck adapter, portable container and offline benchmark harness, see the [runner runbook](../docs/RUNNER.md). Local DuckDB remains the default; remote execution and provisioning are not enabled.

Local, single-writer SQLMesh pipeline for synthetic demos **or verified ingestion snapshots in separate warehouses**. SQLMesh 0.236.4 and DuckDB 1.5.6 were tested with Python 3.13. Full resolved dependency versions are in `requirements.lock.txt`. The Node ingestion prototype remains dependency-free.

From the repository root:

```sh
python3.13 -m venv .local/venv
.local/venv/bin/python -m pip install -r analytics/requirements.lock.txt
.local/venv/bin/python -m unittest discover -s analytics/tests -v
```

Create a fresh demo directory and apply the fixture label:

```sh
.local/venv/bin/python -m analytics.cli --home .local/my-label-demo init-demo
.local/venv/bin/python -m analytics.cli --home .local/my-label-demo add-label analytics/fixtures/historical_label.json
.local/venv/bin/python -m analytics.cli --home .local/my-label-demo resume
```

Initialization refuses to overwrite an existing database. `resume` is a no-op when no changes are pending. The completed development demo is in ignored `.local/sqlmesh-demo/`. No cloud resources, wallets or paid data are involved. SQLMesh telemetry is disabled before Python API imports, and runtime state stays under `.local/`. The lockfile is a tested Python 3.13 environment; other Python/platform combinations require validation. The current dependency stack emits a dateparser deprecation warning on Python 3.13; tests pass.

For end-to-end acquisition with durable discovery and receipt-batch checkpoints, use the [ingestion runbook](../docs/INGESTION.md). Standalone snapshot imports remain available below.

## Load verified ingestion data

First generate `.local/verified.json` using the root README ingestion commands (it is not shipped with the repository). For a fully offline introduction, use [Start here](../docs/START_HERE.md). Use a new directory, separate from any synthetic/legacy demo:

```sh
.local/venv/bin/python -m analytics.cli --home .local/live-analytics load-snapshot .local/verified.json
.local/venv/bin/python -m analytics.cli --home .local/live-analytics resume
```

The first command accepts the v1 JSON emitted by `scripts/ingest.mjs`. The second retries pending snapshot or label work after a failed build/publication. Saved public evidence was loaded locally and rerun without changing the publication. No paid calls or new RPC queries are made by this loader. Importing a saved snapshot does not recheck current canonicality or finality.

The loader replays saved receipts/blocks through the existing Node ingestion canonicalizer, checking derived transfers, memos, accounting and coverage. It stores an immutable normalized-JSON SHA-256 snapshot copy. This checks consistency with the saved source, not cryptographic proofs or the original RPC's truthfulness.

Only positive MPP-v1-tagged ordinary transfers enter the metric models. Mints/burns, zero amounts and untagged/custom-memo movements remain in `raw.movements` with exclusion reasons; failed receipts stay in snapshot evidence. Original uint256 strings are retained. Eligible amounts exceeding DECIMAL(38,0) reject the entire import before committing facts. Aggregate overflow also fails before publication; no float fallback or silent volume exclusion.

Deduplication key is `(chain_id, transaction_hash, canonical_transfer_log_index)`, independent of filename/acquisition time. Overlapping observations add provenance links, not facts. Block/receipt/transfer disagreement for an existing identity rejects the import; automatic reorg reconciliation is not implemented. Exact snapshot reruns are no-ops; a later acquisition creates a provenance observation. JSON formatting/key order is normalized for hashing.

Snapshot copies, acquisition manifests, canonical movements and observation links persist with pending work. SQLMesh conservatively restates the full bounded observed history (maximum span 3660 days); failures retain pending work and the previous publication. Earlier/later history and empty-MPP selections are supported. Live/synthetic snapshots cannot mix, and demo warehouses cannot receive snapshots. Old synthetic label runs receive additive client-field columns as needed.

Outputs retain each source's receipt/token selection, acquisition time, RPC origin, finality limitation and evidence path. `transfer_evidence` links movements to snapshot IDs. Daily/rolling results are **observed selected-payment metrics**: block-range/day/window completeness stays false. Missing dates are unobserved, not zero chain activity. Do not call these ecosystem DAU/WAU or calculate ecosystem churn from them. Tokens/payers are chain scoped; service counts represent server fingerprints, not resolved operators.

Raw client fingerprints are retained, but `originating_interface` remains unknown. `interface_status` distinguishes absent from unresolved fingerprints. Daily/rolling outputs include unknown-interface counts/atomic volume; daily rows also count absent/unresolved fingerprints. No service, intermediary or SDK label fills the interface field by inference. Fingerprint mapping/conflict resolution remains future work.

See [system diagrams](../docs/ARCHITECTURE.md) for evidence flow, storage relationships and recovery.

## Models and workflow ownership

```
raw.transfers + raw.service_labels
                |
       tempo.enriched_transfers     incremental by event_date
          /                  \
tempo.daily_metrics        tempo.rolling_7d
incremental by date        full rebuild of the small pilot
```

SQLMesh owns the dependency graph, materialized tables, intervals, built-in model audits and restatement execution. `workflow.py` owns label validation, source-change detection via submitted assertions, durable pending work and the publication gate. A source-only update needs explicit restatement; model SQL change detection alone is insufficient.

`add-label` validates the assertion and rejects overlapping validity intervals for the same service. Labels cannot be `chain-verified`; they remain operator-reported or model-inferred with their source attached to enriched facts. Labels and pending change records commit together in DuckDB. Reusing an assertion ID with identical content is idempotent; changing content under that ID is rejected.

Affected dates come from the intersection of the label's `[valid_from, valid_to)` interval and existing service activity. Under the writer lock, the workflow unions pending ranges and asks SQLMesh to restate `tempo.enriched_transfers`. SQLMesh propagates execution to dependent daily and rolling models. `rolling_7d` intentionally uses FULL so label effects six days beyond an affected payment are not lost. This favors correctness over efficiency for the bounded pilot; production rolling/cohort models need explicit interval-expansion rules.

The fixture label was recorded February 1 but applies January 2 through January 3. It classifies two payments totaling 500 atomic units as `web_search`. January 1 and January 4 remain unknown; January 9's rolling window gains 300 labeled units. The test also adds a later genuine category change and checks the earlier classification remains intact.

## Storage and publication

- `warehouse.duckdb`: source fixtures, label assertions, pending/applied change records and SQLMesh model/state tables. No separate production state service in this pilot.
- `publications/<sha256>.json`: immutable validated result artifacts with labels, effective dates/provenance, daily and rolling metrics, synthetic coverage and exact string amounts.
- `latest.json`: atomically replaced after built-in and application audits succeed. **This is the serving boundary.** Restatement is not an atomic multi-model update; never expose live internal tables during it.
- `writer.lock`: local process serialization (Unix `fcntl`; not a distributed/cloud lock).

Failures leave work pending and preserve the prior publication. Resume reruns the affected interval and publishes only after conservation/identity, label/provenance and independently recomputed daily/rolling audits pass. A crash after publication but before queue acknowledgment is safe to retry. Immutable artifacts plus atomic replacement protect against process interruption, but power-loss/fsync durability and cloud object-store transactions are not claimed.

Amounts use DECIMAL(38,0), including a fixture above JavaScript's safe-integer boundary. Overflow fails rather than falling back to float. Full uint256 strings are preserved in snapshot/movement evidence; analytical tables accept only checked DECIMAL(38,0) values. The demo bootstrap remains fixture-only; use load-snapshot in a separate directory for acquired live data.

## Verified and remaining scope

The integration test uses real SQLMesh plans and DuckDB, hashes model SQL before/after, and checks historical recategorization, rolling tails, boundary dates, raw fact conservation, provenance, duplicate handling, overlap rejection and recovery after an injected publication failure. A separate test verifies publication refuses stale metrics; assertion validation rejects chain-fact promotion and invalid dates/sources.

Still needed: stronger completeness/metadata gates, registry polling, assertion corrections/retractions and conflict policy, future-only labels, generic vertical attribute tables, operator resolution, additional metrics/cohorts, production state/locking, and scalable targeted rolling rebuilds. The current label table is a narrow service-category contract, not the complete ontology. The demo uses the fixed January 1–10 window. Snapshot calendar/model bounds derive from observed block dates; this is not a coverage guarantee.
