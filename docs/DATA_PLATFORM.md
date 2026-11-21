# Data platform plan

2026-11-18. User-confirmed priority: ingestion, storage and modeling before UX. Primary population is MPP-tagged transfers; broader Tempo transfers are a separate comparison. Architecture below is a recommendation, not deployed infrastructure. Implemented code and live checks are listed in STATUS.md.

## Recommended starting stack

| Responsibility | Starting choice | Why / boundary |
| --- | --- | --- |
| Candidate discovery | Tempo transfers REST API | Public probe succeeded; block bounds and cursor pagination. Treat indexer labels as assertions, not verified memo bytes. |
| Canonical evidence | Tempo JSON-RPC receipts + blocks | Reuse tested normalization; preserve both event indexes, finalized boundary and source. |
| Larger historical backfill | Evaluate cryo logs + blocks | Standard RPC to Parquet, explicit throttles; Tempo compatibility and custom transaction fields untested. Fetch full receipts for candidate transactions before normalization. |
| Raw durable storage | Local immutable files initially; private Cloudflare R2 bucket later | Replayable evidence independent of indexer/model versions. No cloud resource was provisioned. |
| Analytical storage / compute | MotherDuck Lite for v1 (user selected 2026-11-20); local DuckDB for development | Adapter and benchmark harness implemented; real connectivity and representative sizing pending. Preserve portable R2 exports; see BACKEND_DECISION.md. |
| Model orchestration | SQLMesh + DuckDB (user selected) | Frequent historical label corrections favor integrated plans and interval restatement. Native SQLMesh models installed and tested in the local synthetic pilot. See MODELING_DECISION.md. |
| Dashboard serving | Versioned aggregate exports initially; Worker + D1 when needed | Keep dashboard queries small and indexed. D1 is not the raw-history warehouse. |

[Framework decision](MODELING_DECISION.md): user selected SQLMesh with DuckDB on 2026-11-18. Frequent label backfills and AI-assisted development outweigh dbt familiarity. Use native SQLMesh models and a persistent model database, exporting publication artifacts separately; ordinary Parquet objects do not provide transactional table semantics. Keep custom code focused on domain-specific ingestion and evidence/label rules, not a replacement orchestration framework.

MotherDuck Lite is now selected for v1, superseding the earlier local-first cloud-backend recommendation. DuckLake remains a future migration option; see [backend decision](BACKEND_DECISION.md). Use R2 Iceberg/catalog capabilities later if multi-writer table management becomes necessary; they are not prerequisites for v1. Do not place a mutable `.duckdb` file in R2 and treat it as a multi-process database.

## Source evaluation and operational limits

User is open to using their MPP account for valuable gated data (2026-11-18). Paid acquisition is now an option to evaluate; account, endpoint scope and spending limit are not yet specified. No paid calls have been made or enabled. Ordinary validation remains synthetic/free; authenticated data does not become publishable merely because access was purchased.

- Tempo hosted SQL indexer is promising for backfill and aggregation, but the anonymous read-only probe returned HTTP 402. No payment was attempted. Its documentation advertises public low-volume reads; eligibility/quota behavior is unresolved. Do not make it a mandatory dependency yet.
- Tempo transfers REST returned HTTP 200. A returned service attribution did not include raw memo bytes even with `include=memo`; independently inspect receipts. Do not treat formatted amounts, API USD denomination or registry labels as canonical accounting.
- MPPscan has activity, service/resource, stats and timeseries endpoints. Its schema marks activity/stats with SIWX security and 402 responses. Access, historical completeness, license and label verification need checking; use as optional enrichment/cross-check, never the sole denominator. Do not perform registration, signing or payment as part of validation.
- Cryo's own documentation cautions that default concurrency can overload public RPCs. A trial must pin version, set requests-per-second and concurrent-request caps, use a tiny finalized block interval and compare identities/amounts with our receipt pipeline. No compatibility or scale claim has been validated.
- D1 currently documents 500 MB per database on Free, 10 GB on Paid, 100 columns per table and 30-second queries. This favors serving compact results/dimensions rather than repeated full-history joins.
- Cloudflare documents DuckDB integration with its R2 catalog, but table-format integration has version/operation restrictions. Start with ordinary Parquet and versioned manifests; reconsider the catalog when its benefits are needed.

## Ingestion contract

1. Choose a fixed finalized upper block; persist chain, block hashes, source, token universe, topic filters, decoder version and requested range. Never chase a moving head while paginating.
2. Discover all candidates within each bounded interval. `scripts/discover.mjs` currently caps requests at 20 pages, 1000 blocks and 100 selected transaction hashes; the default is 10 pages. It consumes REST cursors and stops on any HTTP error, including 402/429. No credentials/payment middleware.
3. Verify complete receipts and canonical blocks through `scripts/ingest.mjs`. A memo-only log extraction cannot safely deduplicate its companion Transfer event. Keep untagged/custom-memo transfers in scope but exclude them from default MPP metrics.
4. Write immutable raw objects and normalized rows; persist acquisition observations separately from underlying event identity. Only advance a range checkpoint after evidence and manifest validation succeed. Object content hash and canonical event identity provide retry idempotency; duplicate acquisition observations are allowed.
5. Reconcile completed coverage intervals against indexer lag/backfill gaps. Cursor exhaustion means exhausted API results, not proven chain completeness. Retry missing intervals later. Publish a watermark with gaps and token universe; mark partial periods.
6. Reorg/correction creates a new snapshot/model version. Invalidate downstream entity-days, affected periods and first-observed history; never silently append a replacement transfer into totals. Publication switches a manifest pointer only after audits pass.

Steps 1–3 have a bounded manual path and a durable local coordinator. SQLite window/batch checkpoints and immutable snapshot manifests are implemented; range completeness audits and scheduled execution remain future work. Standalone commands keep discovery metadata in a separate file; the coordinator carries discovery context into imported manifests. Both paths still produce receipt-selection coverage, not range-complete coverage. The broad-Tempo comparison currently covers only the selected receipts/tokens, not all Tempo transfers.

## Storage layers and keys

| Layer / table | Grain and important fields |
| --- | --- |
| `acquisition_run` | One attempt: run_id, source, start/end times, bounds, token/filter scope, outcome, schema/decoder versions, request/page counts. Secrets and private identifiers excluded. |
| `raw_object` | One immutable content-hashed object: URI, sha256, byte count, schema version, run_id, access/publication policy. Raw receipts retain source logs. |
| `coverage_interval` | One chain/source/filter interval: inclusive start/end block, boundary hashes, finalized watermark, complete/partial/failed, gaps, run_id. Coverage belongs to a scope, not a global boolean. |
| `fact_transaction` | One chain/tx inclusion: tx hash, block hash/height/time, receipt status, gas/fee evidence. Multiple transfers can share one transaction. |
| `fact_transfer` | One canonical movement inclusion: chain, tx hash, canonical log index, block hash, token, payer, recipient, atomic amount, movement kind, memo/decoder outcome. |
| `transfer_log_evidence` | One canonical movement to one source log: preserve Transfer and TransferWithMemo aliases without duplicating monetary amount. |
| `entity` | Stable internal identity + type: address (chain scoped), token, service fingerprint, service, operator, resource. Avoid merging these types. |
| `attribute_definition` | Namespaced key + version, allowed subject types, scalar type/units, cardinality, allowed values/taxonomy and resolution policy. |
| `attribute_assertion` | One source asserting one typed value about one entity over a valid interval, with recorded time, evidence level, confidence if inferred, source/reference, policy/model version and supersession/retraction links. |
| `relationship_assertion` | One typed entity edge with the same temporal/provenance envelope: service operated_by operator; address receives_for service; resource belongs_to service. |
| `token_metadata_version` | Chain/token, decimals/currency/symbol with effective interval and source; conflicting metadata remains unresolved until a policy selects it. |
| `valuation` | Transfer/token-time + price source/time + quote currency + exact value + method. Nominal USD peg and observed USD valuation are distinct series. |
| `entity_period_activity` | One entity/cadence/period/population/scope/version, preserving distinct entity membership, counts and exact volumes. |
| `metric_publication` | Versioned outputs with population, filters, cadence/window, model/taxonomy/valuation versions, coverage watermark and known/unknown denominators. |

Raw objects: `raw/source=<source>/chain=<id>/date=<UTC-date>/<content-hash>.json.gz`.
Curated snapshots: `curated/schema=<v>/chain=<id>/date=<UTC-date>/<run>-<part>.parquet`.
Publications: `published/model=<v>/<publication-id>/...` plus a manifest naming exact input objects and outputs. Avoid tiny file per transaction, and avoid wallet-address partitioning. Compact into measured batch sizes; never overwrite raw evidence to achieve compaction.

Canonical transfer logical key is `(chain_id, tx_hash, transfer_log_index)`; inclusion key additionally includes block hash. Retain orphaned inclusions outside current canonical views. Public model counts only canonical successful transfer movements; mints/burns and failed transactions have separate views. Do not infer payment role from payer/recipient position alone.

Keep original uint256 values as decimal strings or binary: 78-digit values do not fit ordinary DECIMAL(38). Analytical amount casts must check range and fail/quarantine overflow rather than fall back to float. Aggregate atomic values with arbitrary precision, or validate bounded amounts before fixed-decimal models. D1 publication amounts also remain exact strings; application formatting must not coerce them to unsafe JS Numbers.

## Extensible attributes without losing semantics

Stable high-use facts stay typed columns. New contextual facts become rows, for example:

```
entity: service:synthetic-search
attribute: service.primary_category@v1
value_type: string
value: web_search
valid_from: 2026-11-01T00:00:00Z
valid_to: null
recorded_at: 2026-11-18T00:00:00Z
evidence_level: operator-reported
source_id: synthetic-registry
```

Use separate typed value slots (text, exact numeric string with units, boolean, timestamp, entity reference, or JSON for source extensions), with exactly one populated and validated against the definition. Evidence level is mandatory. Valid time describes the world; recorded time describes what we knew. Never overwrite disagreement or let a later weak inference displace a stronger assertion silently.

Build resolved views such as `dim_service_as_of`, `dim_operator_as_of`, `dim_payer_segment_as_of`, and `fct_mpp_transfer_enriched`. Each resolution must expose selected assertion IDs and conflicts/unknowns. Choose either current corrected taxonomy for all history or as-known historical taxonomy explicitly and version the result. Join one resolved single-valued dimension row per transfer/time before aggregation to prevent fanout. Multi-category exploration may use a bridge but its category totals are not additive; a primary-category policy supplies additive charts.

This permits arbitrarily many registered attributes without repeated table alterations, but not arbitrary ungoverned meaning. A new attribute used as a filter needs a definition, temporal rule, coverage indicator and materialization/index decision. Service fingerprints are observable identifiers; operators and service families require sourced relationships. One fingerprint/domain can cover multiple operations, so endpoint/service-type attribution may remain unknown even when the service is recognized.

## Implemented pilot and remaining acceptance gates

`analytics/` now provides a local DuckDB fixture store, sourced interval labels, a pending/applied change queue, three native SQLMesh models and immutable JSON publications. Source-only label changes explicitly restate history and downstream daily/rolling metrics. This is a narrow category-label slice, not yet the generic attribute design or R2/Parquet persistence. A verified-snapshot bridge now persists raw evidence, acquisition manifests, deduplicated MPP facts and observation links into isolated local warehouses. The first historical-label/retry/conservation acceptance cases pass.


1. Extend the implemented immutable local snapshot store and idempotent loader with coverage-gap reconciliation and explicit inclusion-replacement handling; local discovery checkpoints are implemented. Conflicting canonical evidence currently rejects imports.
2. Snapshot loading, exact checked values, duplicate-key protection and synthetic/live isolation now pass tests. Expand analytical types/metadata and scalable affected-interval rebuilds.
3. Add time-versioned attribute/relationship definitions and resolution views; test conflicting assertions, supersession and as-of joins.
4. Add models in METRICS.md with synthetic histories containing gaps, reactivation, threshold crossings and multiple tokens/services per operator. Run SQLMesh locally with pinned supported versions; validate source-data-only label changes and explicit historical restatement.
5. Measure bytes/block, transfer rate, RPC calls and model runtime on increasing free bounded samples. Estimate history storage/compute cost before cloud provisioning or broad backfill. Budget/freshness/history-start remain open; propose hourly updates and a 30-day complete pilot with earlier first-observed history marked censored.
6. Set up private R2 and scheduled compute after account/budget selection; publish only approved aggregates to simple cards/charts/toggles. D1/Worker serving follows demonstrated query needs.

## Origin/interface identity scope

Keep clientFingerprint separate from serverFingerprint and distinguish originating interface, orchestrator/intermediary, service/operator and SDK/wallet entities. A client fingerprint is a payment-leg memo signal, not proof of UI or request origin. New namespaces should include interface, orchestration, service and payment-client roles, with dated sourced relationship assertions and explicit absent/unresolved/conflicting states. The implemented loader preserves fingerprints and marks interface unknown; mapping registries are not established. Coverage is measured over all eligible selected payments/volume, not only classified activity.

Future journey visualizations must retain unknown origin/stage nodes and typed evidence edges: chain-observed payments versus operator-reported request/tool associations and delivery claims. Do not draw complete journeys by filling gaps with timing or counterparty guesses.


## Cloud execution and client-reference workstream

User-confirmed scope now requires the entire pipeline to run without a laptop or active Codex session. Cloudflare is preferred for scheduling and enrichment; select the actual queue/storage/compute products after checking SQLMesh and DuckDB compatibility. A cloud container runner dispatched by Cloudflare is an acceptable design candidate, not an implemented choice. The new SQLite/file-lock acquisition checkpoints are the local correctness baseline; shared persistence and single-writer coordination must be adapted for cloud operation.

The future client reference is a temporal assertion catalog, not a replacement for immutable payment fingerprints. Store exact identifier bytes/spelling and derived fingerprint, candidate entity and role, source URL plus immutable revision/version, code-path evidence, production/test/example context, first-seen and last-checked times, review status and supersession/conflicts. Recurring bounded public-code discovery feeds candidates to review; approved mappings feed backfill/revalidation. Keep payment tooling, intermediary, purchased service/operator and originating interface distinct. Existing narrow service-category labels do not yet implement these mappings or retractions.
