# Start here

This project turns selected Tempo payment receipts into evidence-aware MPP metrics. Today it runs locally: Node acquires and verifies receipts, DuckDB stores facts and assertions, SQLMesh builds metrics, and a Python workflow publishes audited JSON. The browser is a separate synthetic prototype.

Read this guide, then [system diagrams](ARCHITECTURE.md) and [current state](STATUS.md). No Cloudflare account, wallet, API key or paid service is needed for the walkthrough.

## 1. Prepare a checkout

```sh
git clone --branch main https://github.com/MSilb7/tempo-mpp-dashboard.git
cd tempo-mpp-dashboard
node --version
python3.13 --version
python3.13 -m venv .local/venv
.local/venv/bin/python -m pip install -r analytics/requirements.lock.txt
```

The command checks out `main`. The preview binds only to loopback and serves an explicit allowlist of synthetic UI assets; repository files and `.local/` are inaccessible.

Use Node.js 22+ and Python 3.13 on macOS/Linux (the writer lock uses Unix `fcntl`; native Windows is not supported). Python dependencies are pinned; Node has no dependencies or build step. Initial installation needs package-network access. Subsequent examples are offline. Run all commands from the repository root. The checkout must contain `analytics/` and `scripts/`; see STATUS for remote synchronization status.

## 2. Run ingestion through the models

Choose a new warehouse directory for a clean walkthrough. This generates its own synthetic receipt snapshot; it does not depend on someone else's ignored live files.

```sh
node scripts/demo-ingestion.mjs
.local/venv/bin/python -m analytics.cli --home .local/onboarding-snapshots load-snapshot .local/synthetic-ingestion.json
cp .local/onboarding-snapshots/latest.json .local/onboarding-before.json
.local/venv/bin/python -m analytics.cli --home .local/onboarding-snapshots load-snapshot .local/synthetic-ingestion.json
cmp .local/onboarding-before.json .local/onboarding-snapshots/latest.json
```

Success means a publication exists and `cmp` exits successfully without output: importing the same saved snapshot did not change metrics or provenance. Do not regenerate the snapshot between these two imports: a new acquisition is a new provenance observation, even when payment identities are unchanged. Integration tests additionally cover overlapping selections and re-acquisition without double-counting.

Inspect the local artifact:

```sh
.local/venv/bin/python -m json.tool .local/onboarding-snapshots/latest.json
```

Amounts are exact atomic-unit strings, grouped by token; they are not dollar revenue. Coverage is selected receipts/tokens, not complete days or the Tempo ecosystem. This artifact contains evidence as well as metrics and is not approved for public upload.

## 3. Exercise a historical label backfill

Use a separate warehouse for the purpose-built label demo:

```sh
.local/venv/bin/python -m analytics.cli --home .local/onboarding-labels init-demo
.local/venv/bin/python -m analytics.cli --home .local/onboarding-labels add-label analytics/fixtures/historical_label.json
.local/venv/bin/python -m analytics.cli --home .local/onboarding-labels resume
```

The assertion was recorded February 1 but is valid January 2–4, with an exclusive end. Two historical payments totaling 500 atomic units move from unknown to `web_search`; January 9's rolling window gains 300 labeled units. Total payments and total token volume stay unchanged. `resume` has nothing to do after a successful run. The tests assert these results using real SQLMesh plans.

SQLMesh manages model dependencies and restatements. Our workflow detects submitted source-label changes, records pending work, requests the historical restatement and gates publication. **Editing a source label directly does not automatically schedule a backfill.** Submit assertions through `add-label`; see the [workflow runbook](../analytics/README.md).

## 4. Validate and preview

```sh
node --test test/*.test.mjs
.local/venv/bin/python -m unittest discover -s analytics/tests -v
python3 -m json.tool data/demo.json > /dev/null
node --check app.js
python3 scripts/preview.py
```

Open http://127.0.0.1:8000. The browser reads `data/demo.json`, not your new SQLMesh publication; the serving adapter is future work. Stop the server with Ctrl-C. Tests use synthetic fixtures; the current Python stack may emit a non-fatal dateparser deprecation warning.

## 5. Move to acquired public data

Follow [README ingestion commands](../README.md#ingestion-and-tests) to select bounded public transactions or discover candidates, then verify receipts through a free RPC. Use the generated path, for example:

```sh
.local/venv/bin/python -m analytics.cli --home .local/my-live-warehouse load-snapshot .local/verified.json
```

This loader performs an offline consistency replay, not a new finality check. Keep live data separate from both demo and synthetic snapshot warehouses. HTTP 402/429 stops discovery; do not pay or bypass limits. Do not commit acquired snapshots. Cloud deployment is separate; see [Cloudflare readiness](CLOUDFLARE.md).

For repeated or larger bounded acquisitions, use [durable checkpoints](INGESTION.md) to register windows, resume interrupted batches and track incomplete coverage.

## Common recovery cases

| Symptom | Action |
| --- | --- |
| Demo directory already initialized | Choose a fresh `--home`; initialization deliberately refuses overwrite. |
| Snapshot import or label build/publication failed | Run `resume` against the same home; inspect the error. Previous successful publication remains available. |
| Initial `init-demo` failed | Use a fresh demo directory; bootstrap has no pending label work to resume. |
| Synthetic/live mode mismatch | Create a separate warehouse; never merge modes. |
| Existing payment has conflicting block/receipt evidence | Stop and investigate canonicality; automatic reorg reconciliation is not implemented. |
| Label overlap or reused ID with different contents | Correct the submission design; retractions/supersession are not implemented. |
| Decimal overflow | Import/publication fails; do not cast to float or silently omit volume. |

## Where to change things

| Need | Entry point |
| --- | --- |
| Receipt decoding / canonical movement identity | `lib/tempo.mjs`, `test/tempo.test.mjs` |
| Acquisition / bounded candidate discovery | `lib/ingest.mjs`, `lib/discover.mjs`, `scripts/` |
| Snapshot verification, deduplication, provenance | `analytics/snapshots.py`, `scripts/validate-snapshot.mjs` |
| Label validation, pending work, publication | `analytics/workflow.py` |
| SQL metrics | `analytics/models/`, [metric contract](METRICS.md) |
| Schema and SQLMesh configuration | `analytics/schema.py`, `analytics/config.py` |
| Product intent / framework decision | [PRD](PRD.md), [modeling decision](MODELING_DECISION.md) |
| Current scope, next actions, validation history | [STATUS](STATUS.md), [EVIDENCE](EVIDENCE.md) |

Keep current status, design and evidence updated with substantive changes. Never promote an operator assertion or model inference into a chain fact. An address is not a person; a client fingerprint is not proof of the initiating interface.
