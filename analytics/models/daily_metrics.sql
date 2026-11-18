MODEL (
  name tempo.daily_metrics,
  kind INCREMENTAL_BY_TIME_RANGE (time_column event_date),
  grain (event_date, token, category),
  cron '@daily',
  audits (not_null(columns := (event_date, token, category, payment_count, amount_atomic)))
);

SELECT
  event_date,
  token,
  category,
  COUNT(*) AS payment_count,
  SUM(amount_atomic) AS amount_atomic,
  COUNT(DISTINCT payer) AS active_payers,
  COUNT(DISTINCT service_id) AS active_services,
  COUNT(*) AS unknown_interface_payment_count,
  SUM(amount_atomic) AS unknown_interface_amount_atomic,
  COUNT(*) FILTER (WHERE interface_status = 'absent') AS absent_client_fingerprint_count,
  COUNT(*) FILTER (WHERE interface_status = 'unresolved') AS unresolved_client_fingerprint_count
FROM tempo.enriched_transfers
WHERE event_date BETWEEN @start_ds AND @end_ds
GROUP BY event_date, token, category;
