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
