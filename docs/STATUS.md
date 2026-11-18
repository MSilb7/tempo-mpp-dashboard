# Current state

2026-11-18: initial project brief, evidence model and dependency-free dashboard sketch created. Demo records are synthetic. No live ingestion, registry attribution or operator API integration is implemented.

## Next steps

1. Choose a bounded public Tempo sample and implement a read-only receipt ingestion command.
2. Add tested memo decoding and transfer-event deduplication.
3. Replace synthetic views with persisted evidence and source links.
4. Define a public operator-receipt adapter contract; keep authenticated case studies out of the public dataset.
5. Add coverage denominators before publishing use-case shares.

## Validation

JSON parsing and JavaScript syntax checks are the initial checks. Production browser, ingestion and accounting tests remain to be implemented. Repository publication and Codex project relocation must be verified separately from local file creation.
