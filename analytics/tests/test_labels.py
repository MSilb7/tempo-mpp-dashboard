import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analytics.workflow import PROJECT, connect, ingest_label, init_demo, publish, resume, validate_label

LABEL = json.loads((PROJECT / "fixtures/historical_label.json").read_text())


class LabelWorkflowTest(unittest.TestCase):
    def test_historical_label_restatement_and_recovery(self):
        with tempfile.TemporaryDirectory(prefix="tempo-label-") as directory:
            home = Path(directory)
            init_demo(home)
            baseline = json.loads((home / "latest.json").read_text())
            self.assertEqual({r["category"] for r in baseline["daily"]}, {"unknown"})
            self.assertEqual(sum(r["payment_count"] for r in baseline["daily"]), 6)
            # Hash actual model files to prove this is source-data-only restatement.
            code_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (PROJECT / "models").glob("*.sql")}
            with connect(home) as db:
                raw_before = db.execute("SELECT * FROM raw.transfers ORDER BY transfer_id").fetchall()
            publication = ingest_label(home, LABEL)
            after_bytes = (home / "latest.json").read_bytes()
            after = json.loads(after_bytes)
            known = [r for r in after["daily"] if r["category"] == "web_search"]
            self.assertEqual([(r["event_date"], r["payment_count"], r["amount_atomic"]) for r in known],
                             [("2026-01-02", 1, "200"), ("2026-01-03", 1, "300")])
            self.assertEqual(sum(int(r["amount_atomic"]) for r in after["daily"]),
                             sum(int(r["amount_atomic"]) for r in baseline["daily"]))
            # Boundary dates remain unknown: validity is [Jan 2, Jan 4).
            for day in ("2026-01-01", "2026-01-04", "2026-01-08"):
                self.assertEqual([r for r in after["daily"] if r["event_date"] == day],
                                 [r for r in baseline["daily"] if r["event_date"] == day])
            # The affected Jan 3 transfer still changes Jan 9's rolling window.
            tail = [r for r in after["rolling_7d"] if r["event_date"] == "2026-01-09" and r["category"] == "web_search"]
            self.assertEqual(tail[0]["amount_atomic"], "300")
            self.assertFalse(any(r["event_date"] == "2026-01-10" and r["category"] == "web_search"
                                 for r in after["rolling_7d"]))
            with connect(home) as db:
                self.assertEqual(db.execute("SELECT * FROM raw.transfers ORDER BY transfer_id").fetchall(), raw_before)
                evidence = db.execute("SELECT label_evidence_level,label_source FROM tempo.enriched_transfers WHERE transfer_id='t2'").fetchone()
                self.assertEqual(evidence, ("operator-reported", "synthetic-operator-receipt"))
                self.assertEqual(db.execute("SELECT status,publication_id FROM raw.label_changes").fetchone(), ("applied", publication))
            self.assertEqual(code_before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in (PROJECT / "models").glob("*.sql")})
            # Duplicate delivery is a no-op; conflicting redelivery cannot mutate it.
            self.assertIsNone(ingest_label(home, LABEL))
            self.assertEqual((home / "latest.json").read_bytes(), after_bytes)
            with self.assertRaisesRegex(ValueError, "different content"):
                ingest_label(home, {**LABEL, "category": "enrichment"})
            with self.assertRaisesRegex(ValueError, "Overlapping"):
                ingest_label(home, {**LABEL, "assertion_id": "conflicting-label"})

            # A genuine later category change must not rewrite the previous interval.
            later = {**LABEL, "assertion_id": "later-category", "category": "enrichment",
                     "valid_from": "2026-01-04", "valid_to": None}
            # Simulate failure after SQLMesh rebuilt tables but before publication.
            with patch("analytics.workflow.publish", side_effect=RuntimeError("injected publication failure")):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    ingest_label(home, later)
            self.assertEqual((home / "latest.json").read_bytes(), after_bytes)
            with connect(home) as db:
                self.assertEqual(db.execute("SELECT status FROM raw.label_changes WHERE assertion_id='later-category'").fetchone()[0], "pending")
            self.assertIsNotNone(resume(home))
            final = json.loads((home / "latest.json").read_text())
            self.assertEqual([r for r in final["daily"] if r["category"] == "web_search"], known)
            self.assertEqual([r["amount_atomic"] for r in final["daily"] if r["category"] == "enrichment"], ["500"])
            self.assertIsNone(resume(home))

    def test_invalid_assertions_cannot_become_chain_facts(self):
        for update in ({"evidence_level": "chain-verified"}, {"valid_to": "2026-01-01"},
                       {"recorded_at": "2026-02-01"}, {"category": "unknown"}, {"source": ""}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_label({**LABEL, **update})

    def test_publication_rejects_stale_metrics(self):
        with tempfile.TemporaryDirectory(prefix="tempo-audit-") as directory:
            home = Path(directory)
            init_demo(home)
            published = (home / "latest.json").read_bytes()
            with connect(home) as db:
                db.execute("UPDATE raw.transfers SET amount_atomic=amount_atomic+1 WHERE transfer_id='t2'")
            with self.assertRaisesRegex(ValueError, "Conservation"):
                publish(home)
            self.assertEqual((home / "latest.json").read_bytes(), published)


if __name__ == "__main__":
    unittest.main()
