# Agent entry point

This public repository builds a Tempo MPP analytics dashboard.

Read docs/STATUS.md, docs/PRD.md, docs/TECHNICAL_DESIGN.md and docs/EVIDENCE.md before substantive work. Maintain those sources alongside implementation changes. Keep provider-specific instructions as pointers to this file.

Never commit credentials, private job IDs, user prompts, outputs or authenticated API responses. Use synthetic fixtures unless publication is explicitly authorized. Do not spend funds or submit paid jobs for validation.

Separate chain facts, operator assertions and model inferences in both storage and UI. Report dataset coverage and publication bias. Do not equate addresses with people, transfer volume with revenue, or successful settlement with service delivery.

Prototype validation: `python3 -m json.tool data/demo.json` and `node --check app.js`. Preview using the command in README.md. Add meaningful parser and accounting tests when implementing ingestion. Current prototype has no dependencies or build step.
