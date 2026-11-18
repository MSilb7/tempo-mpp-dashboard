# Current state

2026-11-18: initial project brief, evidence model and dependency-free dashboard sketch created. Demo records are synthetic. No live ingestion, registry attribution or operator API integration is implemented.

## Next steps

1. Choose a bounded public Tempo sample and implement a read-only receipt ingestion command.
2. Add tested memo decoding and transfer-event deduplication.
3. Replace synthetic views with persisted evidence and source links.
4. Define a public operator-receipt adapter contract; keep authenticated case studies out of the public dataset.
5. Add coverage denominators before publishing use-case shares.

## Validation

JSON parsing and `node --check app.js` passed. The public GitHub repository was created and the initial commit pushed to main. Production browser, ingestion and accounting tests remain to be implemented. The checkout has not been registered as a Codex project and this side chat has not been moved; add the folder through the Codex sidebar, then move this chat into that project.
