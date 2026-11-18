# Product brief

## Goal

Make MPP payment flows understandable while exposing the limits of public evidence about underlying use cases.

## Confirmed decisions

- Public repository named tempo-mpp-dashboard.
- Evidence levels: chain-verified, operator-reported, model-inferred.
- Public-chain analytics and published-workflow analytics must remain distinguishable.

## Proposed first release

1. Bounded Tempo payment ingestion with explicit coverage windows.
2. MPP attribution decoding and registry-assisted service labels.
3. Payment detail with inspectable transaction/log evidence.
4. Optional operator receipts joining workflows to payment legs.
5. Coverage metrics for workflow/use-case charts.

## Accounting requirements

Expose gross transfer volume separately from customer charges and provider spending. Count one economic transfer once even if both Transfer and TransferWithMemo logs describe it. Unknown payment roles remain unknown.

## Non-goals for the first release

Global user counts, unqualified revenue estimates, inferred private prompts, paid API execution, or claims that payment proves research delivery.

## Open decisions

Hosting, production framework, indexer backend, historical start block, registry verification and public receipt licensing/retention. The dependency-free sketch does not settle those choices.
