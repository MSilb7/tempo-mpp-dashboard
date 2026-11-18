# Current state

2026-11-18: verified ingestion snapshots now load into SQLMesh with evidence manifests, MPP filtering and overlap-safe deduplication. The saved public sample was imported and an exact rerun left its publication unchanged. The synthetic label/backfill workflow also passes end-to-end. Bounded discovery and receipt ingestion also passed a small public live check. The dashboard remains synthetic; ingestion output is not connected to it. The project is registered in Codex. User confirmed MPP-tagged transfers as primary population, with broader Tempo as comparison; data ingestion/modeling/storage take priority over UX.

## Onboarding and cloud readiness

[Start here](START_HERE.md) runs ingestion, repeat import and historical labeling entirely offline; [system diagrams](ARCHITECTURE.md) show current boundaries and proposed cloud deployment. Cloudflare authenticated account/R2/D1/Workers read probes succeeded on 2026-11-18; nothing was provisioned. See [Cloudflare readiness](CLOUDFLARE.md). A side-chat convenience sample found nonzero client fingerprints in 5/14 selected MPP payments, but established originating interface in 0/14; this is research evidence, not a population estimate or implemented resolver.

## Implemented

- Bounded read-only receipt ingestion: at most 100 transaction hashes and 20 native TIP-20 tokens, expected-chain/finality checks, block membership/hash checks, final canonical-hash rechecks, bounded retries/timeouts/response sizes.
- MPP v1 decoding with absent, non-MPP, malformed and future-version outcomes.
- Adjacent matching Transfer/TransferWithMemo events merge with both source indexes retained. Repeated equal payments remain distinct; unpaired memo events abort accounting.
- Per-token integer totals; mint/burn excluded from gross transfer volume. All payment roles unknown, customer/provider spending null. Operator assertions and model inferences remain separate empty collections.
- Anonymous REST discovery over fixed block bounds with cursor/page limits, token filtering and fail-stop on payment/auth/quota errors. Four new tests bring the suite to 17.
- [Data platform plan](DATA_PLATFORM.md) recommends Tempo REST/RPC, local-to-R2 evidence/Parquet storage, user-selected SQLMesh + DuckDB modeling and compact dashboard serving. Includes temporal extensible attribute/relationship design; not a deployed warehouse.
- [Metric contract](METRICS.md) specifies identity, thresholds, valuation, rolling versus calendar cadence, growth accounting, censored history and segmentation. The first daily/rolling category models are implemented; broader analytical metrics remain to be built.

- Local analytics: native incremental enriched-transfer and daily models, FULL rolling-seven-day model, durable label-change queue, source/effective-date validation, idempotent restatement/resume, conservation audits and atomic publication. See [analytics runbook](../analytics/README.md). Both isolated synthetic and verified-snapshot warehouses are supported; no cloud deployment.

- Verified-snapshot loader: offline replay through the Node canonicalizer, immutable snapshot copies, acquisition/observation links, canonical movement keys, checked decimal amounts, source-mode isolation and resumable SQLMesh builds. Only positive MPP-v1 ordinary transfers enter the primary metrics; all other selected movements remain evidence. Outputs explicitly disclaim complete block/day/rolling coverage.
- Raw client fingerprints now survive SQLMesh; interface remains unknown with absent/unresolved states and unknown-attribution counts/volume. Expanded interface/intermediary/service/SDK scope is recorded in PRD, METRICS and DATA_PLATFORM.

## Framework and paid-source discussion

User selected SQLMesh with DuckDB, prioritizing frequent historical label backfills, AI-assisted development and learning SQLMesh over dbt familiarity. [Framework decision](MODELING_DECISION.md) supersedes the dbt-leaning recommendation. Use native SQLMesh models; build only domain-specific ingestion/label logic ourselves. Source-data-only label changes need explicit affected-interval restatement, not an assumption that model-code change detection handles them. SQLMesh 0.236.4 + DuckDB 1.5.6 is installed in `.local/venv`, with pinned transitive dependencies in `analytics/requirements.lock.txt` (Python 3.13). User remains open to MPP-funded acquisition; no account/spend cap specified and no paid access enabled.

## Next steps

1. Extend the implemented local snapshot manifests/idempotent loader with durable discovery interval checkpoints and provider completeness reconciliation before claiming range coverage.
2. Extend the connected analytics layer beyond checked DECIMAL(38) limits as needed, and optimize conservative full-span snapshot restatements. Extend narrow category labels to temporal attributes/relationships, explicit supersession/retractions and conflict resolution; retain the tested source-change restatement workflow.
3. Build/test the metric contract with synthetic multi-period histories before exposing charts. Resolve initial history, freshness, valuation and spend-tier policies; no invented budget.
4. Measure sample throughput/storage before broad backfill or Cloudflare provisioning. Evaluate cryo only with throttled bounded compatibility checks; hosted SQL currently returned 402.
5. Add registry/operator enrichment and evidence-aware serving views, then minimal dashboard controls. Revalidate virtual-address/guarded-transfer support before expanding normalization.

## Validation

Onboarding follow-up: new offline walkthrough passed in fresh warehouses, including byte-identical repeat publication and label/backfill/resume. All 17 Node and 7 Python tests passed again; documentation file links, demo JSON, app syntax and diff whitespace checks passed. Diagrams are Mermaid source (not render-tested).

Snapshot follow-up: 7 Python tests pass (3 existing plus 4 snapshot integration tests); 17 Node tests pass. Verified exact reruns, overlapping selections, later observations, earlier/later history, source-only labels on imported fingerprints, population filtering, >JS-safe integer precision, empty MPP populations, altered metadata, conflicting canonical evidence, decimal overflow, mode isolation and failed-publication resume. Saved live sample in ignored `.local/live-analytics`: six retained movements, one primary MPP payment; exact reimport leaves publication bytes unchanged. No new RPC or paid requests were needed. Snapshot replay is an as-acquired consistency check, not fresh finality verification.

Python integration suite passed (3 tests), including actual SQLMesh source-only restatement: two historical payments / 500 atomic units move from unknown to web_search; January 9 rolling tail updates; raw facts, total volume and unaffected days remain unchanged. Duplicate delivery, conflicts, later effective-date changes, injected publication failure/resume and stale-metric publication rejection pass. `pip check` passes. Demo is retained in ignored `.local/sqlmesh-demo/`. The pinned stack emits a non-fatal dateparser deprecation warning on Python 3.13. No paid/network acquisition was used for analytics tests.

`node --test test/*.test.mjs` passed (17 tests). Offline ingestion, demo JSON parsing and JavaScript syntax checks passed. Committed-code test fixtures are synthetic. Live anonymous probes: SQL indexer returned 402 (stopped, no payment); transfers REST returned 200; RPC chain ID matched. New discovery CLI found two candidate transactions in a fixed two-block sample; receipt CLI verified both into six canonical movements. Local snapshots remain ignored in `.local/` and are not publishable fixtures. This validates a small sample, not history completeness or indexer scale. No paid jobs, private records or transactions were used. Production browser validation remains outstanding; UI unchanged.

This implementation is prepared on `codex/ingestion-sqlmesh-onboarding` for PR review against `main`. The onboarding clone command selects that branch until merge. No deployment or cloud provisioning is included. Remote publication is verified separately at push time.
