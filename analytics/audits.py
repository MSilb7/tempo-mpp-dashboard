"""Independent publication checks against source facts and temporal assertions."""
from collections import defaultdict
from datetime import timedelta


def audit_models(db, rows):
    expected_facts = rows(db, """
      SELECT t.*, 'unknown' AS originating_interface,
        COALESCE(l.category, 'unknown') AS category,
        l.assertion_id AS label_assertion_id,
        l.evidence_level AS label_evidence_level, l.source AS label_source
      FROM raw.transfers t LEFT JOIN raw.service_labels l
        ON t.service_id=l.service_id AND t.event_date>=l.valid_from
        AND (l.valid_to IS NULL OR t.event_date<l.valid_to)
      ORDER BY t.transfer_id
    """)
    actual_facts = rows(db, "SELECT * FROM tempo.enriched_transfers ORDER BY transfer_id")
    if expected_facts != actual_facts:
        raise ValueError("Label/provenance audit failed; previous publication retained")

    # Python arithmetic and sets provide a check independent of model SQL.
    daily, rolling = defaultdict(list), defaultdict(list)
    calendar = {r[0] for r in db.execute("SELECT event_date FROM raw.calendar").fetchall()}
    for fact in expected_facts:
        day, token, category = (fact[k] for k in ('event_date', 'token', 'category'))
        daily[(day, token, category)].append(fact)
        for offset in range(7):
            window = day + timedelta(days=offset)
            if window in calendar:
                rolling[(window, token, category)].append(fact)
    for model, groups in [('daily_metrics', daily), ('rolling_7d', rolling)]:
        expected = []
        for (day, token, category), facts in sorted(groups.items()):
            amount = sum(int(f['amount_atomic']) for f in facts)
            row = dict(event_date=day, token=token, category=category,
                payment_count=len(facts), amount_atomic=amount,
                active_payers=len({f['payer'] for f in facts}),
                active_services=len({f['service_id'] for f in facts}),
                unknown_interface_payment_count=len(facts),
                unknown_interface_amount_atomic=amount)
            if model == 'daily_metrics':
                row.update(absent_client_fingerprint_count=sum(f['interface_status']=='absent' for f in facts),
                    unresolved_client_fingerprint_count=sum(f['interface_status']=='unresolved' for f in facts))
            expected.append(row)
        actual = rows(db, f"SELECT * FROM tempo.{model} ORDER BY event_date, token, category")
        if actual != expected:
            raise ValueError(f"{model} audit failed; previous publication retained")
