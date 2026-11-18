-- FULL deliberately rebuilds the entire small pilot: a historical correction
-- changes up to six later days even when their transfer partitions are unchanged.
MODEL (
  name tempo.rolling_7d,
  kind FULL,
  grain (event_date, token, category),
  cron '@daily'
);

SELECT
  c.event_date,
  t.token,
  t.category,
  COUNT(*) AS payment_count,
  SUM(t.amount_atomic) AS amount_atomic,
  COUNT(DISTINCT t.payer) AS active_payers,
  COUNT(DISTINCT t.service_id) AS active_services,
  COUNT(*) AS unknown_interface_payment_count,
  SUM(t.amount_atomic) AS unknown_interface_amount_atomic
FROM raw.calendar AS c
JOIN tempo.enriched_transfers AS t
  ON t.event_date BETWEEN c.event_date - INTERVAL '6' DAY AND c.event_date
GROUP BY c.event_date, t.token, t.category;
