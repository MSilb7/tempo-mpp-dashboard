# Product brief

## Goal

Make MPP payment flows understandable while exposing the limits of public evidence about underlying use cases.

## Confirmed decisions

- Public repository named tempo-mpp-dashboard.
- Evidence levels: chain-verified, operator-reported, model-inferred.
- Public-chain analytics and published-workflow analytics must remain distinguishable.
- Prioritize ingestion, data modeling and storage before dashboard UX (2026-11-18).
- Primary v1 population: MPP-tagged transfers; broader Tempo activity is a separately labeled comparison.
- V1 UI can be simple metric cards/charts with date, cadence and segment controls. Detailed UX comes later.
- Use SQLMesh with DuckDB initially; expect AI-assisted development and frequent historical label backfills. SQLMesh learning is welcome; dbt familiarity is not a deciding constraint.

- V1 analytical backend: MotherDuck Lite (confirmed 2026-11-20), retaining SQLMesh and DuckDB SQL. DuckLake is a future migration option. See [backend decision and acceptance work](BACKEND_DECISION.md).

## Analytics requirements

Support transaction and payment-transfer counts, exact payment volume, unique payers/services/operators, per-day or per-period threshold-qualified entities, and daily/weekly/monthly acquisition, retention, resurrection and churn. Filters include token, payer spend tier, observed payer/operator tenure and evolving service categories. Addresses are not people; services are not necessarily operators.

Use a stable typed fact core plus extensible, sourced and time-versioned attributes/relationships. Structured views/materializations expose well-defined metrics without unbounded schema changes or multi-valued join fanout. [Metric contract](METRICS.md) defines proposed cadence, threshold, cohort, valuation and segment rules. [Data platform plan](DATA_PLATFORM.md) compares tools and specifies storage/model grains. These proposed defaults and stack choices are not all confirmed user decisions.

## Client and interface attribution

User-confirmed scope addition: distinguish originating interface, intermediary/orchestrator, purchased service/operator and payment SDK/wallet. A known Mercator/service/SDK identity must never fill an unknown interface by assumption. Preserve raw client/server fingerprints and absent, unresolved or conflicting mapping states. Attribute at payment/request-leg granularity with evidence level, source, effective dates and mapping version; expose interface attribution coverage among eligible transfers and volume, including unknowns.

Current implementation retains client fingerprints and displays interface unknown; no public client mapping has been established. Research population rates, public IDs/registries, role meanings and published leg-level operator receipts. Longer-term interest is an orderflow-inspired origin -> orchestration -> service -> fulfillment visualization. Model evidenced edges and unknown stages; settlement alone proves neither routing nor fulfillment. This is future UX, not a replacement for the data work.

## Proposed first release

1. Bounded Tempo payment ingestion with explicit coverage windows.
2. MPP attribution decoding and registry-assisted service labels.
3. Payment detail with inspectable transaction/log evidence.
4. Optional operator receipts joining workflows to payment legs.
5. Coverage metrics for workflow/use-case charts.

## Accounting requirements

Expose gross transfer volume separately from customer charges and provider spending. Count one economic transfer once even if both Transfer and TransferWithMemo logs describe it. Unknown payment roles remain unknown.

## First implementation slice

Implementation scope (2026-11-18): the first ingestion slice accepts explicit public transaction hashes and a native TIP-20 token allowlist. Bounded block-window candidate discovery is implemented; UI integration remains next. This selected sample is not chain-wide MPP coverage. Memo fingerprints do not prove domain ownership, workflow membership or delivery. Custom/no-memo transfers retain unknown attribution. Gross volume includes any fee/refund transfers selected; mint/burn are separate. Customer/provider spending remains unavailable until role evidence exists. No use-case shares can be derived from this slice.

## Label backfill slice

The first local SQLMesh pilot now reclassifies historical synthetic service activity via a sourced label without modifying model SQL. Daily and seven-day rolling category metrics are restated and published only after raw-fact/volume conservation checks. The narrow category-label workflow is implemented; generic attributes, operator identity and broader growth/cohort metrics remain planned. Verified ingestion JSON now loads into isolated SQLMesh warehouses with explicit selected-sample coverage and source provenance.

## Non-goals for the first release

Global user counts, unqualified revenue estimates, inferred private prompts, paid API execution, or claims that payment proves research delivery.

## Paid source preference

User is open to using their MPP account for valuable gated data. Evaluate source coverage, cost, account integration and reuse/publication rights; this is not an unspecified spending authorization. Free/synthetic validation remains the default.

## Open decisions

Exact surrounding cloud products/costs, historical start block, spend-tier boundaries, valuation sources, registry verification and public receipt licensing/retention. Selected v1 analytical backend is MotherDuck Lite with SQLMesh; proposed surrounding services are Tempo REST/RPC, R2/Parquet and small serving marts; SQLMesh/DuckDB dependencies are installed for the local synthetic pilot, while cloud resources remain unprovisioned. The dependency-free sketch does not settle those choices.


## Confirmed cloud execution and enrichment scope — 2026-11-18

The whole pipeline must be cloud-runnable: ingestion, public-code discovery/enrichment, storage, SQLMesh modeling/backfills, publication and dashboard serving. Codex is a development environment, not a production runtime dependency. Cloudflare is preferred; evaluate SQLMesh/DuckDB runtime compatibility and a suitable cloud container runner dispatched by Cloudflare if needed. This is required future scope, not authorization to spend or a claim of deployment.

Maintain a growing client-fingerprint reference table with exact UTF-8 clientId string, Keccak prefix, candidate identity, semantic role, immutable source revision/URL, supporting code context, production versus test/example usage, first-seen/last-checked times and review status. Payment tooling must remain separate from originating interface, intermediary/orchestrator and purchased service/operator. Preserve candidates, approved sourced mappings, conflicts, unknowns and version history; string/hash matches do not authenticate software.

A recurring discovery job should find exact public identifiers, trace them into payment memo construction (excluding unrelated OAuth fields), hash and deduplicate candidates while retaining provenance, and queue review. Approved additions, corrections and retractions must flow into historical backfill/revalidation as assertion machinery evolves. Cloudflare is the preferred runner; trigger, queue, bounded inspection/hash work, storage and review/backfill orchestration remain product-selection/design work. No recurring job is deployed. The unresolved research fingerprint documented in EVIDENCE stays unresolved and its originating interface stays unknown.

## Backend execution policy — 2026-11-20

Target $0/month MotherDuck and inexpensive overall operation. Start with daily refresh, bounded history expansion and batched backfills. Serve validated precomputed publications; pause or slow refresh before overages. Paid usage/upgrades need approval and free-tier cutoff must be verified before unattended use. Before a larger MotherDuck subscription, compare a small persistent-disk VM with ordinary DuckDB/SQLMesh and explicit backup/restore/operations costs; DuckLake is a later fallback.

The connection adapter, portable container definition and offline benchmark harness are implemented. Remote compatibility, container execution and production sizing remain acceptance work, not deployment claims. See [runner setup](RUNNER.md).
