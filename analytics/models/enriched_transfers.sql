MODEL (
  name tempo.enriched_transfers,
  kind INCREMENTAL_BY_TIME_RANGE (time_column event_date),
  grain transfer_id,
  cron '@daily',
  audits (unique_values(columns := (transfer_id)), not_null(columns := (transfer_id, event_date, category)))
);

SELECT
  t.transfer_id,
  t.event_date,
  t.service_id,
  t.payer,
  t.token,
  t.amount_atomic,
  t.synthetic,
  t.client_fingerprint,
  t.interface_status,
  'unknown' AS originating_interface,
  COALESCE(l.category, 'unknown') AS category,
  l.assertion_id AS label_assertion_id,
  l.evidence_level AS label_evidence_level,
  l.source AS label_source
FROM raw.transfers AS t
LEFT JOIN raw.service_labels AS l
  ON t.service_id = l.service_id
  AND t.event_date >= l.valid_from
  AND (l.valid_to IS NULL OR t.event_date < l.valid_to)
WHERE t.event_date BETWEEN @start_ds AND @end_ds;
