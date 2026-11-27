# Technical design

[System diagrams](ARCHITECTURE.md) visualize these contracts; [Start here](START_HERE.md) is the teammate walkthrough.

## Selected cloud target

MotherDuck Lite is the selected v1 analytical backend; SQLMesh and DuckDB dialect remain. Proposed execution uses Cloudflare orchestration and a portable Linux container, with validated publications as the serving boundary. A managed PostgreSQL state connection needs validation/provider selection. [Backend decision](BACKEND_DECISION.md) defines required scale/backfill/recovery benchmarks and portable backend boundaries; a small VM with ordinary DuckDB is the first alternative before a larger subscription, with DuckLake a later option. The adapter and portable container definition are implemented, with offline configuration and local benchmark tests. Container build and network-disabled execution passed CI on 2026-11-21. Real MotherDuck/PostgreSQL connections and cloud deployment remain unverified. See [runner runbook](RUNNER.md).

## Current implementation

Static HTML/CSS/JavaScript sketch consumes data/demo.json. All fixtures are synthetic; the UI must state this. No external network calls other than fetching the local fixture. `scripts/preview.py` binds to loopback and serves only the four synthetic UI assets, excluding ignored evidence and repository metadata.

## Ingestion implementation

The maintained next-stage architecture is [DATA_PLATFORM.md](DATA_PLATFORM.md): source evaluation, local-to-R2 storage, typed facts plus temporal extensible attributes, user-selected SQLMesh + DuckDB (decision in MODELING_DECISION.md) and serving boundaries. [METRICS.md](METRICS.md) owns metric/segment definitions. Local SQLMesh warehouses now support synthetic demos and isolated verified-snapshot imports; the complete architecture remains planned.

## Implemented local analytics slice

`analytics/` pins SQLMesh 0.236.4 + DuckDB 1.5.6 with a complete Python 3.13 dependency lock. Three native SQL models form the graph: incremental enriched transfers -> incremental daily category metrics and FULL seven-day rolling metrics. Raw selected MPP facts, source/effective-date label assertions and pending/applied changes persist in DuckDB alongside SQLMesh state. Date intervals are UTC and label validity ends are exclusive. The fixed January 1–10, 2026 calendar belongs only to the synthetic demo. Snapshot warehouses derive bounds from observed block dates, without claiming complete periods.

The project workflow validates labels, rejects overlaps/conflicting ID reuse, commits labels with pending work, identifies affected historical dates, and explicitly calls SQLMesh restatement. SQLMesh handles dependent model execution; the FULL rolling model deliberately rebuilds its later windows. Raw analytical facts retain source mode and exact DECIMAL(38,0) amounts; label evidence is separate operator-reported/model-inferred provenance. The snapshot loader preserves original uint256 strings in evidence and rejects eligible values outside DECIMAL(38,0); aggregates also fail on overflow.

Publication validates fact preservation, no join fanout and per-token total conservation. It also checks current temporal label/provenance assignments and independently recomputes every daily/rolling metric using Python integer arithmetic and sets (`analytics/audits.py`), preventing stale categories, distinct counts or rolling windows from passing merely because totals match. Immutable JSON artifacts and an atomic `latest.json` replacement separate successful publication from in-place model rebuilds. Failed runs leave changes pending for idempotent resume; local file locking serializes writes. There is no distributed/cloud transaction, production state database, generic assertion resolver, retraction workflow yet. Verified snapshots are now bridged through analytics/snapshots.py; [analytics/README.md](../analytics/README.md) is the executable runbook.

The independent Node.js 22+ command is `scripts/ingest.mjs`. `lib/tempo.mjs` handles decoding/normalization; `lib/ingest.mjs` handles acquisition. No dependencies were introduced. `scripts/demo-ingestion.mjs` exercises the same pipeline with synthetic in-process RPC fixtures.

`scripts/discover.mjs` / `lib/discover.mjs` now add anonymous Tempo REST candidate discovery over a fixed block interval with cursor pagination, token selection, request/response budgets and immediate stop on 402/429. Discovery output can be passed directly to the receipt command. API attribution labels are ignored; raw receipt memos determine membership. Cursor exhaustion is not proof of indexer completeness. Empty windows are saved explicitly but cannot be passed to the nonempty receipt selection command.

## Implemented receipt ingestion contract

- Input: expected Tempo chain ID string, 1–100 transaction hashes, 1–20 native TIP-20 addresses. Bounds apply before deduplication; casing is normalized. No automatic discovery, pagination or operator API access.
- RPC allowlist: `eth_chainId`, `eth_getTransactionReceipt`, `eth_getBlockByNumber`. HTTPS only, redirects disabled, three attempts per call, ten seconds per attempt, eight MiB per response. Endpoint comes from an environment variable; only its origin is persisted, excluding paths/query strings. Use a free public provider; metered providers are outside the validation contract.
- Acquire a finalized boundary, require receipts at/below it, check receipt/log block identity and transaction membership, then recheck all canonical block hashes and the boundary. Unsupported finality, missing receipts and inconsistencies abort. Failed transactions with no logs remain evidence with zero movements.
- Output: versioned JSON snapshot with raw receipts/blocks, acquisition time, RPC origin (or synthetic source label), canonical transfers, per-token totals and coverage. CLI creates output only after successful validation and refuses to overwrite existing files. Store output in ignored `.local/`.
- `chain-verified` means fields checked against RPC receipts/blocks, not independent cryptographic receipt/consensus verification. `verificationMethod` and finality limitations travel with the data. Synthetic fixtures use `evidence: synthetic`; their RPC finality is simulated.

## Normalization and accounting

Transfer has three topics, TransferWithMemo four. Memo is indexed topic 3; amount is the sole 32-byte data word. Address topics require zero padding. Repeated identical log indexes collapse; conflicting duplicates abort. The Transfer index defines canonical identity, scoped by chain/transaction with block hash retained.

Attach only an immediately following matching TransferWithMemo (same token, payer, recipient, amount), preserving both indexes. Pair each alias once, preserving repeated equal payments. Unpaired memo events abort. This conservative rule rejects unsupported layouts, including virtual-address cases with different physical/logical recipients. Other events and non-allowlisted tokens remain in raw evidence but do not enter totals.

Memo decoding checks exact length, tag and version; anonymous client fingerprints become null. Decoding assigns no domain, workflow, service or economic role. All roles remain unknown; separate `operatorAssertions` and `modelInferences` arrays are empty. No hash-only workflow join is attempted.

BigInt atomic amounts serialize as decimal strings. Totals remain per chain/token, with no dollar conversion or inferred decimals. Zero-address mint/burn movements have separate totals. Customer/provider spending is null; unknown-role volume equals gross transfer volume. Reprocessing is deterministic except acquisition time; the Python snapshot loader merges overlapping observations by canonical identity without duplicating payments.

## Coverage and trust boundaries

Coverage records explicit selection, allowlist, receipt count and observed block span. `completeForSelection` does not imply `completeForBlockRange`; chain population and workflow denominators are null. Selection/publication bias is explicit. The RPC is trusted for correctness/completeness, including potentially omitted logs: consistency checks cannot prove every log was returned. Network upgrade behavior, persistent reorg handling and independent-provider validation remain future work. Durable local acquisition checkpoints are implemented below. UI integration must expose these qualifications.

## Verified snapshot boundary

`load-snapshot` replays saved receipts/blocks via `scripts/validate-snapshot.mjs`, using the same Node ingestion parser. It verifies derived transfers, totals and coverage against that replay; it makes no fresh network/finality checks. Normalized JSON is content-addressed and copied into ignored warehouse storage. Snapshot metadata keeps source, acquisition time, selections and finality limitations. Separate movement/receipt/block tables check identity consistency; observation links record repeated acquisitions. Canonical payment identity remains chain + tx hash + canonical log index. Conflicting inclusions fail closed pending explicit reorg reconciliation.

The primary raw analytical table contains only positive ordinary MPP-v1-tagged transfers. Other movements and failed receipts remain archived evidence with exclusion reasons. Chain-scoped payer/token IDs prevent cross-chain aggregation; service identifiers are raw server fingerprints, not operators. Client fingerprints remain distinct; absent/unresolved interface states and unknown interface count/volume are exposed. No client mapping or SDK/orchestrator interpretation is inferred.

New source observations and pending labels trigger conservative restatement of the full bounded observed span, with complete rolling rebuilds. Atomic validated publication remains the serving boundary. Exact snapshots are no-ops; overlapping or re-acquired snapshots add provenance without counting payments twice. Imports cannot mix live/synthetic modes or reuse a legacy demo warehouse. History is bounded to 3660 days and input snapshots to 128 MiB. Range/day/window completeness is always false for these receipt samples; missing dates are unobserved and no ecosystem growth claims follow.

## Target pipeline

Tempo RPC/indexer -> raw receipts/logs -> canonical transfers -> MPP memo decoder -> attribution registry -> optional operator receipt adapters -> analytical views.

## Proposed canonical records

- Transfer: chainId, transactionHash, logIndex, blockNumber, blockHash, timestamp, token, amountAtomic, decimals, payer, recipient, memo, finalityStatus.
- Attribution: serverFingerprint, clientFingerprint, challengeReference, decoderVersion; keep domain claims and verification evidence separate.
- Workflow assertion: issuer, publicWorkflowId, nodeId, operationId, category, status, publishedAt, sourceUrl, signature and publication policy.
- Payment link: workflow/node, chainId, transactionHash, logIndex, role, assertion source. A hash-only link must be resolved or marked ambiguous if multiple transfers qualify.

Preserve raw evidence, acquisition time and source. Use integer token units; never floating-point accounting. Normalize duplicate event representations without discarding provenance. Handle pagination, retries, reorgs and finality before claiming complete coverage.

Operator signatures establish attributable assertions, not truth of delivered work. HTTP challenge references can bind a known challenge to a payment; they do not automatically join separate upstream and downstream purchases.


## Durable bounded acquisition

`analytics/ingestion.py` uses a separate SQLite checkpoint database and the existing local writer lock. It registers immutable jobs and fixed inclusive windows, commits each completed discovery result with deterministic receipt-batch selections, fsyncs content-addressed snapshots before storing their references, then imports through `load_snapshot`. Imported acknowledgment follows successful model publication; replay after an intervening crash is safe. Discovery interrupts restart the current window; receipt interrupts repeat only an uncheckpointed batch. The range-end block hash is pinned and rechecked on pending-job resume. Explicit observation keys permit later rescans of an identical interval without conflating them with retries.

Status queries use a read-only SQLite transaction without the acquisition writer lock, so progress remains inspectable during network/model work. The checkpoint ledger owns requested, empty and pending window coverage. Imported snapshots carry validated discovery context into SQLMesh manifests; neither layer claims provider or full-range completeness. Individual batches can publish before a whole job finishes. See [runbook and recovery diagram](INGESTION.md) for bounds, storage and failure semantics. Cloud execution requires durable shared storage, a cloud-safe single-writer strategy and scheduling; current filesystem paths/locks are local.

## System acceptance

`analytics.evaluate` replaces external transport with synthetic responses while running production discovery/receipt parsing, acquisition, replay/import, modeling and publication. Fixed expected totals plus a negative-control test provide an independent acceptance signal. Reports expose named failures for future agent-proposed improvements. [Evaluation contract](EVALUATION.md) distinguishes offline coverage from live/cloud/UI acceptance and defines the reviewed improvement loop.

## Known-case replay boundary

A user-supplied funding transaction can be checked alongside operator-reported provider-payment references. Verify each reference against chain receipts, keeping the operator's node-to-payment mapping distinct from chain facts. Funding and provider legs both contribute to gross MPP flow; neither payment-leg count nor gross volume is a tool-call count or customer-spend metric. Untagged transfers and burns remain evidence with existing population exclusions. Saved live cases stay private; CI uses invented receipt patterns and independent expected counts.
