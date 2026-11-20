# Agent entry point

This public repository builds a Tempo MPP analytics dashboard. Teammates start with [docs/START_HERE.md](docs/START_HERE.md) and [system diagrams](docs/ARCHITECTURE.md).

Read docs/STATUS.md, docs/PRD.md, docs/TECHNICAL_DESIGN.md and docs/EVIDENCE.md before substantive work. Maintain those sources alongside implementation changes. Keep provider-specific instructions as pointers to this file.

Never commit credentials, private job IDs, user prompts, outputs or authenticated API responses. Use synthetic fixtures unless publication is explicitly authorized. Do not spend funds or submit paid jobs for validation.

Separate chain facts, operator assertions and model inferences in both storage and UI. Report dataset coverage and publication bias. Do not equate addresses with people, transfer volume with revenue, or successful settlement with service delivery.

Validation: `python3 -m json.tool data/demo.json`, `node --check app.js`, and `node --test test/*.test.mjs`. Exercise offline ingestion with `node scripts/demo-ingestion.mjs`. Preview using the command in README.md. Node.js 22+ ingestion and the static prototype have no dependencies or build step. Live snapshots belong in ignored `.local/`; the UI still accepts synthetic data only.

Analytics uses pinned SQLMesh + DuckDB on Python 3.13; setup and local label workflow are in analytics/README.md. Run `.local/venv/bin/python -m unittest discover -s analytics/tests -v`. Use `load-snapshot` in an isolated warehouse for verified ingestion JSON; `init-demo` remains synthetic-only. Never mix live and synthetic data. Source-label changes require explicit restatement; serve validated publication files, not partially rebuilt internal tables.

Durable acquisition uses `python -m analytics.ingestion` with separate checkpoint and warehouse directories; see docs/INGESTION.md. Completed work is not complete-chain coverage. Keep checkpoint databases, discovery output and acquired snapshots in ignored `.local/`.
