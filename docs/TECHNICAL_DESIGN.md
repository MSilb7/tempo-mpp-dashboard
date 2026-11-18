# Technical design

## Current implementation

Static HTML/CSS/JavaScript sketch consumes data/demo.json. All fixtures are synthetic; the UI must state this. No external network calls other than fetching the local fixture.

## Proposed pipeline

Tempo RPC/indexer -> raw receipts/logs -> canonical transfers -> MPP memo decoder -> attribution registry -> optional operator receipt adapters -> analytical views.

## Proposed canonical records

- Transfer: chainId, transactionHash, logIndex, blockNumber, blockHash, timestamp, token, amountAtomic, decimals, payer, recipient, memo, finalityStatus.
- Attribution: serverFingerprint, clientFingerprint, challengeReference, decoderVersion; keep domain claims and verification evidence separate.
- Workflow assertion: issuer, publicWorkflowId, nodeId, operationId, category, status, publishedAt, sourceUrl, signature and publication policy.
- Payment link: workflow/node, chainId, transactionHash, logIndex, role, assertion source. A hash-only link must be resolved or marked ambiguous if multiple transfers qualify.

Preserve raw evidence, acquisition time and source. Use integer token units; never floating-point accounting. Normalize duplicate event representations without discarding provenance. Handle pagination, retries, reorgs and finality before claiming complete coverage.

Operator signatures establish attributable assertions, not truth of delivered work. HTTP challenge references can bind a known challenge to a payment; they do not automatically join separate upstream and downstream purchases.
