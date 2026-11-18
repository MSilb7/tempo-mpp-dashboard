# Metric and segment contract

2026-11-18. User requested transactions, payment volume, unique services/operators/payers, thresholded active entities, acquisition/retention/churn, daily/weekly/monthly cadences and filters. These definitions are proposed defaults unless explicitly labeled confirmed. The local synthetic pilot implements daily and seven-day rolling category counts/volumes/distincts; verified snapshots now feed those same models with selected-sample coverage; the broader metrics below remain planned.

## Population, units and identity

Confirmed: primary population is canonical successful **MPP-v1-tagged transfer movements**. Label this precisely: the memo pattern is observable but spoofable, and some MPP payments use custom/no attribution memos. Do not claim this is all MPP. Future known versions require decoder support. Exclude mint/burn and failed receipts. Preserve zero amounts in evidence, but default active/paid-volume population requires amount > 0; expose zero-value event counts separately.

Broader selected Tempo transfers are a separate comparison population with their own coverage. No registry-registration requirement for primary population; unregistered fingerprints remain included. Do not count companion TransferWithMemo as another payment.

Payer = chain-scoped sending address, not human/customer. Service fingerprint, resolved service and resolved operator are separate grouping options. Operator/service count uses only resolved identities and always reports unresolved coverage. Multiple receiving addresses can map to one operator; identical recipient does not automatically merge services. User-facing payer “spending” is outgoing selected payment volume unless customer-role evidence is available. Keep customer spending and downstream provider spending distinct and nullable.

## Metric definitions

| Metric | Definition |
| --- | --- |
| Payment transfers | Distinct canonical positive transfer IDs in chosen population/filter/time range. |
| Transactions | Distinct `(chain, tx_hash)` containing at least one qualifying transfer. One transaction can contain many payments. |
| Gross payment volume | Sum canonical transfer amounts, per token; multi-token USD only through explicit valuation method/coverage. Not revenue or unique economic demand. |
| Active payers | Distinct chain-scoped payer addresses making at least one qualifying transfer. |
| Active service fingerprints | Distinct decoded server fingerprints, including unresolved fingerprints. Separate from resolved services. |
| Active services / operators | Distinct resolved IDs receiving qualifying activity; show unknown/unresolved transfer and volume shares. |
| Payers above X | Aggregate qualifying outgoing volume per payer/period first, then count entities with value strictly > X. |
| Operators above X | Aggregate qualifying incoming volume across each resolved operator's mapped services/addresses first, then count strictly > X. |
| Customer / provider spending | Only role-attributed transfers, with assertion provenance, unknown-role denominator and role-policy version. Otherwise unavailable, not zero. |

Threshold basis is selectable: per-token atomic/display units, nominal USD for known USD-denominated tokens, or observed USD valuation. Nominal USD is a peg assumption, not a market price. Never assume any token named USD is worth $1. Missing token metadata/prices/roles produce unknown eligibility; show eligible, excluded and unknown counts/volume coverage. Use exact arithmetic and explicit rounding only at display boundaries.

“Above X in a day” and “above X over the selected period” are different modes. For the daily-qualified mode at weekly/monthly display cadence, union distinct entities whose daily totals exceed X on at least one day; do not sum daily entity counts. Period-qualified mode sums the full period first. Default threshold comparison is strictly greater; label it accordingly.

## Calendar and rolling windows

Proposed timezone is UTC for reproducibility. Half-open intervals `[start, end)` throughout. Calendar days start 00:00 UTC, weeks start Monday, months start on the first. Do not call a 30-day interval a calendar month.

- Calendar activity/granularity: daily, weekly, monthly buckets.
- DAU: trailing one complete UTC day; WAU: trailing seven complete UTC days; MAU: trailing thirty complete UTC days, labeled rolling 30-day. A later local-time option changes model/query keys.
- Date range controls display, not the available lookback used to compute first-observed history, churn or rolling windows. Read sufficient history before the selected display start.
- Incomplete trailing periods are flagged provisional and excluded from comparable growth/churn by default. Missing coverage is unknown, never zero activity.
- Distinct weekly/monthly counts are recomputed from underlying entity membership, not summed from daily counts. Persist entity-day membership and transfers/dimensions sufficient to answer supported filters exactly.

## Growth accounting

Use nonoverlapping complete calendar periods at selected cadence. Let `A_t` be the active entity set under the fixed population/filter/threshold definition for period t, and `H_<t` all observed active entities before t.

```
retained_t    = A_t intersect A_(t-1)
new_t         = A_t minus H_<t
resurrected_t = (A_t minus A_(t-1)) intersect H_<t
churned_t     = A_(t-1) minus A_t
active_t      = retained_t + new_t + resurrected_t          [counts]
active_t - active_(t-1) = new_t + resurrected_t - churned_t [counts]
retention_t   = |retained_t| / |A_(t-1)|
churn_rate_t  = |churned_t| / |A_(t-1)|
```

Zero denominator => null, not zero. Churn means absent in this next complete period, not permanently lost. Calendar growth accounting is distinct from overlapping rolling WAU/MAU charts. Also support cohort retention: cohort = first observed eligible period; retention at offset k = cohort entities active in that offset / original cohort size. A cohort that has not reached offset k is null, not zero.

Names must say “newly observed” until prehistory is established; a 30-day backfill cannot prove address creation or first-ever use. If earlier history is incomplete, the residual new-vs-resurrected split is censored/unknown rather than confidently new. If the preceding period has coverage gaps, suppress churn/retention and flag the accounting series. Track left-censoring alongside first-observed dates.

For segmented growth, default to fixed cohort membership determined at acquisition/first observed eligible period. Dynamic current-spender or age segmentation has movement between segments; report entrants/exits separately, not as product acquisition/churn. New-to-service and new-to-ecosystem are separate scopes. Threshold crossings similarly mean qualifying/unqualifying, not necessarily new/churned payers. The activity predicate, segment policy and mapping version must remain consistent across compared periods.

## Segments

| Segment | Proposed rule |
| --- | --- |
| Payment token | Chain + contract; symbol only a label. Multi-token selections require explicit value basis. |
| Payer spend tier | Based on trailing 30 complete days ending before period start, to avoid future leakage. Configurable fixed lower/upper bounds, versioned. Low `[0,L)`, medium `[L,H)`, high `[H,infinity)`; unknown separate. No arbitrary dollar defaults selected yet. |
| Payer age | Days since first observed qualifying MPP activity, measured at period start. Explicitly observed tenure, not wallet/person age. |
| Operator age | Days since first observed qualifying activity attributable to operator under stated mapping version. Newly registered label is not a newly operating business. |
| Age bands | `<7 days`, `7–29`, `30–89`, `90–364`, `365+`, unknown/censored. Exact day boundaries avoid ambiguous “month” lengths. New within period has age band `<7` at first activity. |
| Service type | Versioned controlled taxonomy; initial candidates web_search, data_extraction, enrichment, model_inference, media_generation, infrastructure, other, unknown. These are proposed labels, not observed counts. |
| Payment role | Customer charge / provider spend / refund / fee / unknown only when supported; role evidence stays separate from transfer fact. |

One service may expose multiple types of resources. Without an operation-level link, do not assign a payment to a particular endpoint or operation. Use service primary category at the documented granularity or unknown; multi-label exploratory charts require explicit non-additivity warnings.

## Materializations and query behavior

### Label changes and historical restatement

Frequent label-driven backfills are a confirmed requirement. SQLMesh + DuckDB is selected. The narrow service-category workflow is now implemented and tested in analytics/; broader operator/cohort impacts, general conflict resolution and live ingestion remain an implementation contract.

1. Append a sourced, versioned label assertion. Distinguish a newly discovered historical fact from a real change in the entity's classification. Discovery time is not automatically the effective start date; unknown validity must remain explicit.
2. Resolve assertions under a named policy, preserving conflicts and evidence levels. Keep raw transfers unchanged. A label correction does not change chain-verified amounts.
3. Produce a change manifest identifying affected entities, effective intervals, prior/new label versions, source and reason. Source data can change without any model SQL change; explicitly request SQLMesh restatement rather than expecting code-change detection to find it.
4. Rebuild affected enrichment partitions and dependent aggregate periods. Include rolling-window tails; if first-observed/cohort assignment changes, rebuild all dependent later periods as needed. Where impact cannot be bounded safely, rebuild the full affected model history.
5. Audit conservation of unsegmented transfer counts/volume, no temporal join fanout, correct unknown-to-known coverage shifts, unchanged unaffected results and retry idempotency. Operator distinct counts and categorized totals may legitimately change. Publish a new version after audits, retaining the previous publication for comparison.

The first acceptance scenario starts with an unknown service in historical synthetic payments. Add a label with an explicit historical validity interval without changing model SQL; restate through SQLMesh; verify that historical service/category/operator views update, raw payment facts and overall volume remain unchanged, rolling/cohort dependencies refresh and a repeated run produces identical results. Also test a genuine category change with a later effective date so earlier history stays unchanged.

Proposed graph: raw snapshots -> canonical transfer facts -> memo population -> as-of resolved dimensions/valuation -> payer-day and service/operator-day membership -> calendar/rolling entity-period models -> growth/cohort models -> publication marts.

Keep a stable core relational schema and vertical assertions in DATA_PLATFORM.md. Promote commonly filtered attributes into versioned dimension views/materializations; do not join unrestricted assertions directly into sums. Preserve low-grain data for supported filter combinations; precomputed global distinct counts cannot answer arbitrary intersections. Avoid an unlimited cross-product cube.

Metric API contract: population, measure, entity_grain, date_from/to, timezone, calendar_cadence or rolling_days, threshold_mode/value/basis, filters, segment_policy and model_version. Response includes data, unit, value_basis, coverage, provisional periods, unresolved/censored counts and freshness. Simple cards/charts/dropdowns can consume this later without embedding business logic in UI components.

Validation gates: companion-log deduplication; distinct tx vs transfer counts; exact amounts and missing valuation; temporal joins with no fanout; multiple services per operator; unioned weekly distincts; strict threshold equality; calendar boundary cases; reactivation; partial/missing periods; left-censored history; cohort maturity; fixed vs dynamic segment migration; zero denominators; both growth identities above.

## Originating-interface attribution and sample coverage

Confirmed dimensions: originating interface, intermediary/orchestrator, service/operator and payment SDK/wallet are separate. Never substitute a recognized intermediary or SDK for an unknown originating interface. Keep raw client/server fingerprints; mapping requires a sourced, versioned, temporally valid role assertion for the relevant leg. Absent client signal differs from unresolved mapping or conflicting claims. The current implementation supports absent/unresolved fingerprints and interface unknown; no mappings are accepted yet.

Interface coverage denominator is all eligible positive MPP transfers (and their per-token volume), including unknowns. Report known-interface payment/volume shares and unknown counts/volume; classified-only shares must be labeled conditional on classified data. Current daily and rolling metrics expose unknown counts/atomic volume, and daily metrics expose absent/unresolved client-signal counts. Raw client fingerprints are not named applications or people.

Verified receipt imports are still selected samples: their daily and rolling results count observed selected payments only, not full ecosystem activity. Every publication retains false range/day/window completeness, unknown chain/workflow denominators, acquisition provenance and selection bias. No completeness, retention or churn inference can be derived from an absent day.

## Attribution coverage interpretation

Report client-fingerprint presence, resolved client identity/role and known originating interface as separate coverage measures, each with the eligible-payment denominator and separately per-token volume. A populated or hash-matched client field must not count as a known interface. The November 18 side-chat convenience sample had 5/14 populated clients but 0/14 established interfaces; see [evidence and sampling limitations](EVIDENCE.md#client-fingerprint-convenience-sample-handoff--2026-11-18). These are selected-payment counts, not ecosystem prevalence or volume shares. The current implementation still treats all interfaces as unknown.
