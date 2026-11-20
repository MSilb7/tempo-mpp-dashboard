# Tempo MPP Dashboard

Explore machine-payment activity without confusing settled transfers with workflow purpose.

The dashboard is a synthetic prototype. A separate dependency-free Node.js command ingests bounded, read-only Tempo receipts; its output is not yet connected to the UI. No operator integration is connected.

## Start here

Follow the [offline onboarding walkthrough](docs/START_HERE.md), then read the [system diagrams](docs/ARCHITECTURE.md). The walkthrough generates its own data and exercises ingestion, rerun safety and historical label backfill. [Cloudflare readiness](docs/CLOUDFLARE.md) records verified connector access and the remaining deployment decisions.

For bounded multi-window jobs with durable resume and automatic SQLMesh imports, see [durable ingestion and recovery](docs/INGESTION.md).

## Ingestion and tests

Requires Node.js 22 or newer. No install or build step.

```sh
node --test test/*.test.mjs
node scripts/demo-ingestion.mjs
```

The second command runs entirely offline and writes `.local/synthetic-ingestion.json`. All fixture identifiers are invented.

Optional public candidate discovery: put `chainId`, integer `fromBlock`/`toBlock` (inclusive, at most 1000 blocks), `tokens` and optional `maxPages` (1–20, default 10) in `.local/window.json`. Choose a fixed finalized range. Then:

```sh
node scripts/discover.mjs .local/window.json .local/discovery.json
TEMPO_RPC_URL=https://rpc.tempo.xyz node scripts/ingest.mjs .local/discovery.json .local/verified.json
```

Discovery is anonymous and read-only; any HTTP error, including 402/429, stops without payment. It limits selected candidates to 100 transactions, ignores API attribution labels, and cannot prove indexer completeness. Empty discovery results need no receipt run. Keep both files: discovery holds pagination/range metadata, while verification describes receipt-selection coverage.

For public-chain ingestion, create `.local/selection.json` containing a `chainId` string (`"4217"` for mainnet or `"42431"` for Moderato), `transactionHashes` (1–100 full transaction hashes), and `tokens` (1–20 native TIP-20 addresses). Select only public transactions you intend to inspect. The command reads every log in those receipts but accounts only for allowlisted tokens.

```sh
TEMPO_RPC_URL=https://YOUR_FREE_PUBLIC_TEMPO_RPC node scripts/ingest.mjs .local/selection.json .local/sample.json
```

Supply a free, read-only RPC endpoint; no wallet or signing key is used. The command never sends transactions or submits jobs. Output creation is exclusive: choose a new filename for each snapshot. `.local/` is ignored by Git; do not commit acquired data without publication review. Only the RPC origin is saved for provenance; endpoint paths, query strings and provider errors are excluded.

This is an explicit transaction sample, **not a block-range indexer**. Coverage is complete only for selected receipts/tokens. Missing receipts, unsupported finality, inconsistent blocks, malformed transfer events or unpaired memo events abort the run. Amounts are decimal strings in atomic units, grouped per chain/token; decimals and spending classifications remain unknown. See [technical design](docs/TECHNICAL_DESIGN.md) for assumptions and limitations.

## Preview

Run `python3 scripts/preview.py` in this directory and open http://127.0.0.1:8000.

## SQLMesh + DuckDB pilot

The [analytics setup and workflow](analytics/README.md) now implements historical service-category labeling and backfill with real SQLMesh plans. Install the pinned Python 3.13 environment and run its tests:

```sh
python3.13 -m venv .local/venv
.local/venv/bin/python -m pip install -r analytics/requirements.lock.txt
.local/venv/bin/python -m unittest discover -s analytics/tests -v
```

`analytics.cli init-demo`, `add-label`, and `resume` provide pending-change tracking, historical restatement, audits and atomic publication. Verified ingestion JSON can now feed those models in a separate warehouse:

```sh
.local/venv/bin/python -m analytics.cli --home .local/live-analytics load-snapshot .local/verified.json
```

Only positive MPP-v1-tagged transfers enter primary metrics. Selected evidence and per-snapshot coverage/provenance are retained; repeat/overlapping imports do not duplicate payments. Live and synthetic data cannot mix. These outputs describe selected receipts, not complete chain/day coverage. See the analytics guide for limits. No cloud warehouse is deployed.

## Project context

Read [AGENTS.md](AGENTS.md), [product brief](docs/PRD.md), [technical design](docs/TECHNICAL_DESIGN.md), and [current state](docs/STATUS.md).

The [data platform plan](docs/DATA_PLATFORM.md) covers source/tool choices, storage and extensible modeling. The [metric contract](docs/METRICS.md) defines activity, growth accounting, cohorts and segments. Daily category metrics and seven-day rolling metrics now run locally on synthetic demos or isolated verified-snapshot data; broader metrics and cloud serving remain planned.

## Evidence model

- Chain-verified: transfer amounts, addresses, timestamps, fees and memo bytes.
- Operator-reported: workflow membership, service operation, use case and completion.
- Model-inferred: predictions with provenance and uncertainty; never silently promoted to fact.

Gross transfer volume is not end-user expenditure: customer and downstream provider payments may represent the same economic purchase.
