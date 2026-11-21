# System acceptance and improvement loop

The offline system eval executes production discovery parsing → receipt verification/MPP parsing → durable acquisition checkpoints → snapshot replay/import → SQLMesh → audited JSON publication. Only external transport responses are synthetic. It uses isolated temporary local DuckDB storage and refuses remote backends; it cannot spend money or modify an existing warehouse.

```sh
.local/venv/bin/python -m analytics.evaluate --report .local/system-eval.json
# Inside the portable image:
docker run --rm --network none tempo-analytics:local analytics.evaluate
```

The CLI exits nonzero on failure and emits a versioned JSON report with named checks, failed stage, error type, elapsed time and explicit limitations. The optional report contains results only, not receipts or credentials; it belongs in ignored `.local/`. SQLMesh also emits progress to stdout, so use `--report` for a standalone machine-readable JSON file. In CI, the report is visible in job logs; durable cross-run history/artifact collection is not yet implemented.

## Acceptance contract

The invented fixture has one receipt with two distinct payments, each represented by adjacent Transfer/TransferWithMemo logs, and values above JavaScript's safe integer limit. Discovery returns duplicate candidate rows across two pages. Fixed expected results are **two payments and 18014398509481986 atomic units**. These expectations are independent of parser/model output; publication audits also recompute metrics independently.

The eval requires exact totals, unknown categories before labeling, selected-sample coverage, discovery provenance, byte-identical exact reruns, stable metrics across overlapping observations, historical relabeling, unchanged raw facts, recovery after injected publication failure, preservation of the previous validated artifact and fail-closed discovery on HTTP 402. Negative controls corrupt the published count, remove the provenance manifests and substitute an unrelated acquisition error for HTTP 402; each must fail the eval. The provenance check requires the expected two pages/two API rows/one deduplicated candidate. HTTP 402 must come from the production discovery parser’s exact rejection; a generic subprocess failure cannot satisfy it.

Existing focused tests remain necessary: they cover mixed non-MPP populations, empty windows, chain/source inconsistency, corrupt snapshots, process death, interval consistency and broader label/metric cases. The system eval complements those tests and the performance benchmark; it is not a substitute for either. There is no averaged score that can hide a failed correctness or provenance check.

## What this does not prove

- Synthetic transport cannot establish live provider availability, schema stability, finality or completeness. A future bounded free-source canary should record freshness, parse rejection reasons, selections and unknown-attribution rates without treating sparse activity as a pipeline failure. Do not enable paid access or expand history automatically.
- Publication here means the local audited JSON boundary. Cloud upload, public projection, dashboard fetch/render, production scheduling and distributed writer coordination remain separate acceptance work.
- No actual MotherDuck/PostgreSQL connection is tested. The local container is the offline execution target.
- Elapsed time is diagnostic, not a stable CI performance threshold or cloud billing estimate.

## Improving the system safely

1. Run these gates on every candidate PR, locally and in the network-disabled container. The CI workflow now includes an explicit system-eval step.
2. Classify a failure by stage and named check. Preserve a sanitized, minimal synthetic reproduction; never promote acquired receipts, credentials or private outputs into a public fixture.
3. Have an agent propose a targeted fix and add a regression that fails before the fix. For discovery/label-quality improvements, establish reviewed expected labels and provenance first; do not let model assertions become their own ground truth.
4. Compare the candidate against the same acceptance suite and representative benchmark dimensions. Correctness, deduplication, coverage and publication-preservation checks must all pass. Treat timing as a separate signal.
5. Review and merge the candidate, then add the failure case to the permanent corpus. Changing metric semantics or expected totals requires an explicit contract decision; do not make the test green by weakening it.

**Implemented:** deterministic eval, structured diagnostics, negative control and CI hooks. **Not implemented:** a scheduled live canary, cross-run trend storage or an autonomous agent that opens/fixes/merges PRs. Those can consume this report later; this change enables measurement and regression protection, not unreviewed self-modification. Start with agent-proposed fixes in reviewed PRs before considering broader automation.
