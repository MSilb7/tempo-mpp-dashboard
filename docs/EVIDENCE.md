# Research basis

Reviewed 2026-11-18. Revalidate evolving implementations before production ingestion.

- MPP memo implementation: https://github.com/wevm/mppx/blob/main/src/tempo/Attribution.ts
- Tempo charge draft: https://paymentauth.org/draft-tempo-charge-00.pdf
- Mercator documentation: https://mercator.sh/docs
- Mercator API schema: https://mercator.sh/openapi.json
- MPPscan registry schema: https://mppscan.com/openapi.json

## Findings from an exploratory case study

A customer payment and ten provider payments could be correlated from timing, amounts and memo attribution. An authenticated Mercator job record subsequently supplied explicit node-to-transaction mappings. The ten reported settlements matched public transaction receipts. The workflow assignment remained an operator assertion; no on-chain parent/job link was established. Private identifiers and payloads are deliberately not included here.

Mercator exposes payments.legs with nodeId, serviceId, payer, recipient, amount, currency, network and optional reference/explorerUrl. Its public receipt is a limited presentation; authenticated job access is not equivalent to public availability. A public-data indexer cannot assume authenticated records are available for every workflow.

Memo v1 layout: 4-byte tag, 1-byte version, 10-byte server fingerprint, 10-byte client fingerprint, 7-byte challenge-derived reference. Fingerprints are labels, not proof of address ownership.

## Implementation verification — 2026-11-18

Inspected upstream sources through web tools; no authenticated records or paid calls:

- [mppx Attribution.ts](https://github.com/wevm/mppx/blob/main/src/tempo/Attribution.ts): v1 offsets above; tag is Keccak-256 of `mpp`, first four bytes (`ef1ed712`); zero client fingerprint denotes anonymous client. Future versions remain unsupported.
- [viem Tempo ABI](https://github.com/wevm/viem/blob/main/src/tempo/Abis.ts): TransferWithMemo indexes sender, recipient and memo; amount is uint256 data. The inspected generated ABI names Tempo revision `6ef1f812c9ddcbe90a88ada73944012520942d26`. Signature hashes are constants in `lib/tempo.mjs`; Ethereum Keccak-256 is not SHA3-256.
- [Tempo TIP-20 implementation](https://github.com/tempoxyz/tempo/blob/main/crates/precompiles/src/tip20/mod.rs): ordinary `transfer_with_memo` performs the transfer then emits the memo event; tests expect both. Newer virtual-address paths can differ in physical/logical recipients. This slice rejects mismatched pairs. Mutable `main` sources require revalidation before extending support.

Reproduce validation with `node --test test/*.test.mjs` and `node scripts/demo-ingestion.mjs`. All fixture addresses, hashes and amounts are invented. Tests cover repeated payments, duplicate/conflicting logs, memo byte boundaries/versions, large integer amounts, mint/burn exclusion, separate tokens, failed receipts, selection limits, missing/mismatched receipts, canonical hash changes, bounded retries/response sizes and sanitized errors. These tests do not establish live-chain completeness or production readiness.

## Source/storage/modeling evaluation — 2026-11-18

- [Tempo indexer](https://tempo.xyz/developers/docs/api/indexer-api) documents SQL access over PostgreSQL/ClickHouse; [query reference](https://tempo.xyz/developers/docs/api/indexer) caps rows/time. [Authentication](https://tempo.xyz/developers/docs/api/authentication) describes public quota and optional paid MPP. **Observed:** one anonymous bounded SELECT probe returned 402. No payment, wallet or credentials used. Public-quota availability is unresolved; do not assume docs imply free SQL access in this environment.
- [Transfers API](https://tempo.xyz/developers/docs/api/transfers) documents block filters, cursor pagination and memo enrichment. **Observed:** anonymous probe returned 200. A service attribution label was present without raw memo bytes. New bounded CLI then discovered two transactions in two blocks; public RPC verified both into six movements. Raw output is ignored locally, not a repository fixture. No claim of historical completeness.
- [MPPscan schema](https://mppscan.com/openapi.json) offers services, activity and timeseries; declares SIWX security/402 on activity/stats. Optional enrichment subject to access, licensing and coverage checks, not assumed freely available.
- [Cryo](https://github.com/paradigmxyz/cryo) supports standard RPC logs/blocks and Parquet output; explicitly recommends requests-per-second/concurrency limits with third-party RPCs. Tempo-specific compatibility remains untested.
- [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) document 500 MB Free / 10 GB Paid per database and 30-second query limits. [D1 FAQ](https://developers.cloudflare.com/d1/reference/faq/) describes per-database single-threaded query execution. Assessment: use for compact serving tables, not raw analytical scans.
- [Cloudflare DuckDB catalog integration](https://developers.cloudflare.com/r2-data-catalog/config-examples/duckdb) documents R2/Iceberg connectivity with version/operation restrictions. Assessment: start with ordinary Parquet and manifests; defer catalog complexity.
- [SQLMesh DuckDB integration](https://sqlmesh.readthedocs.io/en/latest/integrations/engines/duckdb/) warns local DuckDB state is unsuitable for shared production state; recommends a robust state database such as PostgreSQL. [Time-range models](https://sqlmesh.readthedocs.io/en/stable/examples/incremental_time_full_walkthrough/) support interval replacement/lookback. Assessment: useful for evolving taxonomy and backfills.
- [dbt-duckdb](https://github.com/duckdb/dbt-duckdb) supports external files and incremental table models; a credible alternative if dbt familiarity wins. At the time of comparison neither framework was installed; SQLMesh was subsequently selected by the user (see decision below).

## Framework follow-up — 2026-11-18

[MODELING_DECISION.md](MODELING_DECISION.md) records refreshed primary sources and the revised recommendation. Key corrections: dbt-duckdb supports microbatch time-range models, SQLMesh now identifies as a Linux Foundation project, and current dbt v2 DuckDB support differs from the Python adapter with documented parity/extension limitations. No framework was installed or benchmarked. The user is open to paying for useful MPP-gated acquisition; no paid call or account integration occurred in this comparison.

## Confirmed modeling decision — 2026-11-18

User selected SQLMesh with DuckDB, citing AI-assisted development, interest in SQLMesh and expected frequent label backfills. This supersedes the interim dbt-leaning recommendation. MODELING_DECISION.md records the custom-code boundary; METRICS.md specifies label-change restatement and acceptance criteria. This turn updated design/decision records only; no framework installation, benchmark or paid request occurred.

## SQLMesh label/backfill acceptance — 2026-11-18

Installed SQLMesh 0.236.4 and DuckDB 1.5.6 into isolated `.local/venv` using Python 3.13; resolved transitive dependencies are locked in `analytics/requirements.lock.txt`. Consulted SQLMesh plans/DuckDB docs and inspected the installed Python Context API. Production initial plans cannot set start/end without restatement; bootstrap uses the model start plus a fixed execution time. Source-data-only changes use explicit `restate_models` and start/end dates. Python API telemetry is disabled before imports; runtime files remain local.

`python -m unittest discover -s analytics/tests -v` passed 3 tests with real local SQLMesh/DuckDB execution. Historical label effective January 2–4 (exclusive end), recorded February 1, reclassified two payments / 500 atomic units. January 9 rolling output changed by 300 labeled units; raw facts, total amounts and unaffected daily results were preserved. SQL model hashes were unchanged. Tests also verify idempotent duplicate submission, interval conflict rejection, later category change, publication failure/retry and rejecting stale-metric publication. DECIMAL amounts above the JavaScript safe integer range remain exact strings in JSON. The complete model graph currently uses one synthetic token and service-category labels; no operator/cohort or live-data coverage claim follows.

The 17 Node tests, offline ingestion, demo JSON parse, app syntax and `pip check` also passed. A non-fatal upstream dateparser deprecation warning occurs on Python 3.13. No paid jobs, credentials or live data were needed for this implementation.

## Verified ingestion to SQLMesh — 2026-11-18

The snapshot loader now replays v1 saved evidence through the existing Node receipt canonicalizer before accepting derived transfers, memo attribution, totals and coverage. It preserves immutable snapshots and per-acquisition metadata separately from canonical movements and observation links. Actual saved public ingestion data was loaded into ignored `.local/live-analytics`: six movements preserved, one positive MPP-v1 payment in daily/rolling metrics. Exact reimport left publication bytes unchanged. This was offline use of previously acquired public evidence; no new RPC, paid calls or authenticated records were used. Finality remains as-acquired RPC evidence, not a fresh chain check.

Seven Python tests pass, including overlapping snapshots, fresh observations of existing transfers, earlier/later date expansion, labels on imported fingerprints, full-precision amounts above JS safety, empty MPP selections, tampering/coverage mismatch rejection, canonical conflict/reorg rejection, decimal overflow rejection, live/synthetic isolation and failed-publication recovery. All fixture identifiers are invented. The 17 Node tests remain passing. Selected-sample completeness flags stay false at range/day/window level.

## Origin/client scope handoff — 2026-11-18

User-authorized side-chat findings were incorporated into product/model/metric scope. The existing [MPP attribution source](https://github.com/wevm/mppx/blob/main/src/tempo/Attribution.ts) includes an optional client fingerprint; zero bytes decode as null. The loader retains this leg-level signal and distinguishes absence from unresolved mapping while leaving originating interface unknown. A known service, intermediary or SDK does not prove the initiating UI.

Research leads supplied by the side chat: [Mercator docs](https://mercator.sh/docs) describe orchestration across agent clients and downstream services; [mppx changelog](https://github.com/wevm/mppx/blob/main/CHANGELOG.md), entry 1d08567, describes CLI User-Agent attribution from environment signals. These are off-chain enrichment leads, not verified public mappings or proof of UI. Public client registry/population coverage and reliable leg-level interface joins remain unestablished. The side chat could not access MPPscan schema (separate from this chat's earlier successful schema inspection). No paid/private records were used. orderflow.art was suggested as future visualization inspiration and was not inspected; inferred complete journeys must not be rendered as chain-verified flows.

## Client-fingerprint convenience sample handoff — 2026-11-18

A user-authorized side-chat reported four anonymous REST convenience slices (50 rows per slice, up to 20 distinct selected transactions per slice), verified in memory through the existing RPC ingestion checks. Across 80 selected receipts, 163 canonical movements included 14 positive MPP-v1 payments in 14 transactions. Five of those 14 payments had a nonzero client fingerprint (35.7%); nine had none (64.3%). Actual initiating interface was established for zero: all 14 remain interface-unknown.

The short UTC slices ended around 20:52, 19:52 and 14:52 on November 18 and 20:52 on November 17. These convenience observations are not representative prevalence estimates, complete block windows or volume-weighted attribution rates. Raw snapshots were not persisted; this is a reported research handoff, not an independently replayable repository fixture.

Four populated client fingerprints matched a hash of the explicit candidate `mercator.sh`; one remained unresolved. The side-chat tested 751 candidate strings drawn from 140 public directory entries plus explicit candidates and checked the hash implementation against test vectors. A hash match is a candidate identity mapping, not authentication of the emitting software or proof of upstream UI. One reported leg matched Mercator as client and OpenRouter as service; other matches had the same candidate client/server identity. This supports keeping client role separate from purchased service and initiating interface. No mapping resolver has been added to the models.

The public directory lead is https://mpp.dev/api/services. MPPscan activity/services requests returned 402 and stopped without payment. No raw transactions, authenticated payloads or private identifiers are recorded here.

## Onboarding and Cloudflare access — 2026-11-18

Added a self-contained offline walkthrough and Mermaid diagrams for acquisition/modeling, provenance relationships, label restatement/recovery and the explicitly proposed cloud architecture. Cloudflare connector account discovery plus R2, D1 and Workers list routes succeeded using authenticated GET requests only. No cloud resources changed; no credentials, account inventory or authenticated response payloads were saved to the repository. Read access does not prove deployment permissions or billing readiness.

Executed the new walkthrough in fresh ignored warehouses: offline ingestion, snapshot load, exact repeat with byte-identical publication, demo initialization, historical label submission and no-op resume all passed. Relative Markdown file links resolve; 17 Node tests and 7 Python integration tests passed, along with demo JSON parsing, app syntax and `git diff --check`. Mermaid source diagrams were reviewed but not rendered in this validation. Dependencies used the existing pinned environment; a fresh package installation was not repeated. At that validation checkpoint changes were local/uncommitted. The subsequent publication preparation uses `codex/ingestion-sqlmesh-onboarding` and updates the walkthrough to select it pending merge.


## PR #1 correctness and onboarding review — 2026-11-18

Review found two substantive gaps: conservation alone could publish stale labels or incorrect daily/rolling aggregates, and the generic repository-root HTTP server exposed ignored local evidence. Added source-label/provenance comparison plus independent Python recomputation of all published metric fields; regression tests corrupt outputs while preserving raw totals. Replaced the preview command with a loopback-only asset allowlist and tested private paths and traversal rejection. Initial demo-bootstrap failure is now distinguished from resumable snapshot/label failures in the walkthrough.

Added `.github/workflows/validate.yml` to validate pinned dependency installation, Node/Python tests and the full offline walkthrough on a fresh hosted runner. Action usage follows the official [checkout](https://github.com/actions/checkout), [setup-node](https://github.com/actions/setup-node) and [setup-python](https://github.com/actions/setup-python) instructions reviewed November 18. Workflow permissions are read-only; it uses synthetic data and does not upload artifacts or access cloud accounts. The walkthrough now selects `main` for the merged result. Local Python regression suite: 9 tests pass. Remote check/merge status is recorded on [PR #1](https://github.com/MSilb7/tempo-mpp-dashboard/pull/1).

## Public-code client reference scope handoff — 2026-11-18

User-authorized side-chat research reports a bounded scan of 16 accessible public repositories and one published npm package, not exhaustive ecosystem coverage. It checked Keccak empty-input and Transfer-signature vectors, then computed exact UTF-8 string prefixes. The production Tempo request CLI sets `tempo-wallet` and passes it into charge-path client attribution: [pinned charge source](https://github.com/tempoxyz/wallet-rs/blob/9dcaa938066e6f9fad5098a03def66254e7751ff/crates/tempo-request/src/payment/charge.rs#L26). The reported prefix is `0x94def446126a9a3ee57c`. This is a source-backed candidate for **payment tooling**, not authentication of the emitting software or evidence of originating interface.

`my-app` and `cli` in [Rust attribution tests](https://github.com/tempoxyz/mpp-rs/blob/main/src/tempo/attribution.rs), and `client-app` in [pinned Python tests](https://github.com/tempoxyz/pympp/blob/2d7beedec905f9cdfd4e4e263ab970497c17a833/tests/test_tempo.py), are test/example identifiers, not established production app identities. The reported published `@frames-ag/payment-tempo` 0.0.1 source passes through optional clientId without a constant. Unrelated OAuth client IDs must be excluded from candidate discovery.

The unresolved observed target fingerprint (identifier excluded from this public repository) remains PRESENT but identity UNRESOLVED and originating interface UNKNOWN. Its purchased service cannot establish its app identity. These are research handoff findings, not a deployed resolver or independent re-verification in this implementation. The growing reference table, recurring reviewed enrichment and whole-pipeline cloud execution requirements are now recorded in PRD and DATA_PLATFORM. No cloud resources, recurring automation or paid calls were created.


## Durable acquisition checkpoint verification — 2026-11-19

Added SQLite jobs/windows/batches with synchronous transactions, fixed finalized range anchors, immutable fsynced snapshot files and post-publication acknowledgment. Receipt snapshots carry validated discovery context into SQLMesh source manifests. Requested, empty and pending windows remain in the checkpoint ledger; completed work never asserts chain completeness. Deterministic inputs resume an existing job; explicit observation keys support later rescans.

Validation passed 19 Node and 14 Python tests. A child process exits abruptly after actual SQLMesh publication, leaving no acknowledgment; resume reuses its saved snapshot and completes remaining work. Overlapping jobs plus a same-range rescan retain three canonical payments / 600 atomic units, identical daily/rolling metrics and eight acquisition-observation links. Tests also cover interrupted discovery/receipt acquisition/import, empty windows, completed no-op reruns, changed anchors/source, corrupted files and invalid completeness claims. The Node adapter independently tests finalized bounds, chain identity and existing discovery/receipt verification. All fixtures are synthetic; no live requests, credentials, paid jobs or cloud deployment were used. Existing CI discovers the new test files automatically. This implementation remains local/uncommitted at this checkpoint.


## Checkpoint PR review — 2026-11-20

Review identified that `status` acquired the long-lived writer lock and could block throughout ingestion. It now uses a read-only SQLite transaction without the acquisition lock, rejects missing stores without creating files, and validates the checkpoint schema version. A regression test invokes the real status CLI while another process holds the writer lock, verifies pending progress and confirms unchanged database bytes. Malformed RPC URLs now produce a generic error without echoing sensitive input; subprocess calls retain the original configured endpoint if the ambient environment changes. Synthetic credential markers test redaction; no real credentials are used.

The observed unresolved research fingerprint was omitted from the public documentation changes; public source-code examples and derived candidate hashes remain distinguished from acquired payment evidence. Source, tests and documentation only are intended for this PR; ignored live data, checkpoints, logs and warehouse files stay local.

Review validation: 19 Node and 16 Python tests pass, including the new concurrent status and RPC-redaction regressions. Offline ingestion, JSON/syntax checks, `pip check`, documentation file links and diff checks pass. File inventory excludes runtime artifacts; credential-pattern matches are intentional synthetic rejection-test URLs only.

Remote publication and final CI/merge status are tracked in [PR #2](https://github.com/MSilb7/tempo-mpp-dashboard/pull/2).


## MotherDuck Lite decision handoff — 2026-11-20

User selected MotherDuck Lite for v1, retaining SQLMesh/DuckDB dialect and keeping DuckLake as a future migration option. [Backend decision](BACKEND_DECISION.md) records the required incremental, historical-service and broad-taxonomy benchmarks, recovery/interval/publication checks, adapter/export/container portability and explicit upgrade boundary. Official MotherDuck pricing and SQLMesh MotherDuck integration documentation were checked during reconciliation; pricing is a dated reference, not benchmark evidence or a forecast. Managed PostgreSQL state remains a recommendation to validate, not a selected provider. No account setup, backend migration, provisioning or paid benchmark was performed. This update changes documentation only.


## 2026-11-20 — Backend adapter and portable runner

Implemented centralized local/MotherDuck connections, target-bound homes, current-catalog metadata checks, UTC SQLMesh configuration and optional separate PostgreSQL state. MotherDuck tests mock the driver and test opt-in rejection; they do not demonstrate real service compatibility. Local DuckDB remains the default. The PostgreSQL configuration test mocks the optional driver; the cloud requirements file installs it for actual image use.

All 22 Python tests pass, including the existing snapshot overlap/process-recovery suite and a 16-day synthetic benchmark beyond the original demo bounds. The benchmark checks raw-fact invariance, independent metric audits, duplicate-label idempotency, failed-publication preservation, retry and persisted incremental intervals. Unavailable scan/rewrite/billing telemetry is null, not zero; local resource sampling records restrictions. These tiny fixtures establish correctness, not production sizing.

Added a non-root Python 3.13/Node 22 container definition with an allowlisted build context and a network-disabled CI smoke job. Docker/Podman are unavailable locally; image build/run and the new CI job have not executed. No remote database connections, live acquisition, provisioning or paid benchmarks were performed. New execution documentation is in RUNNER.md; budget and fallback decisions are maintained in BACKEND_DECISION.md.

Remaining offline checks also pass: 19 Node tests, synthetic ingestion, demo JSON parsing, app syntax and diff whitespace. No live artifacts or credentials were added to the implementation/build context.


## Adapter/container review — 2026-11-21

Review removed an extra restatement from the incremental benchmark: normal refresh now uses SQLMesh run and a second no-op refresh verifies byte-identical publication. SQLMesh's NOTHING_TO_DO result is accepted as a successful retry. Failed session setup now closes the acquired database connection, with a mocked credential-safe regression. State documentation specifies an isolated state database per analytical target. MotherDuck/PostgreSQL tests remain offline/mocked; no paid or live warehouse benchmark was run. Container acceptance is gated on the PR's network-disabled smoke job.

Review validation passes 23 Python tests and 19 Node tests, offline ingestion, JSON/app syntax and diff whitespace checks. The reviewed Git file inventory contains source, synthetic fixtures/tests and documentation only; credential-signature checks found no real secrets.

Both jobs passed in [CI run 44869402477](https://github.com/MSilb7/tempo-mpp-dashboard/actions/runs/44869402477) for commit `1dde2ec`: offline validation/onboarding and container build plus network-disabled Python tests and synthetic benchmark. This supersedes the earlier image-unverified status. PR #3 records final CI/merge status. Remote MotherDuck/PostgreSQL connectivity remains untested.


## Offline system eval — 2026-11-21

`analytics.evaluate` passes all 14 named checks on synthetic transport responses through production discovery pagination, receipt parsing, checkpoints, snapshot import, SQLMesh and publication. A separate negative-control test corrupts the published payment count and confirms the eval reports failure. Remote-backend execution is rejected before acquisition. The complete local suite passes 26 Python and 19 Node tests; Node syntax, demo JSON and whitespace checks pass. The new explicit CI eval steps are local changes and have not run remotely. No live requests, paid benchmarks, provisioning, scheduled jobs or autonomous code changes were enabled. See EVALUATION.md for scope and the proposed reviewed improvement loop.


## End-to-end eval review — 2026-11-21

Review fixed two false-positive paths: generic acquisition failures could satisfy the HTTP 402 rejection check, and an empty provenance list could pass an `all(...)` check. The synthetic bridge now reports the production parser's specific 402 outcome, while other errors fail the eval. Provenance must contain the expected two-page/two-row/one-candidate discovery record. Added negative controls for missing manifests and unrelated source errors. No transport reaches live services; CI container execution disables networking.

Review validation passes 28 Python tests and 19 Node tests, offline ingestion, Node syntax, demo JSON, documentation links and whitespace checks. Only source, synthetic test fixtures and documentation are included; local eval reports, credentials and acquired data remain excluded.

[PR #4](https://github.com/MSilb7/tempo-mpp-dashboard/pull/4) is the authoritative final remote CI and merge record, including the container eval. Earlier statements that the new CI hooks were unexecuted describe the initial local implementation checkpoint.
