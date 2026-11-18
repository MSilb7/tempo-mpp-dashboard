"""Shared narrow raw schema. Live receipt evidence is stored separately in snapshots."""


def create_raw(db):
    db.execute("""
        CREATE SCHEMA raw;
        CREATE TABLE raw.transfers (
          transfer_id VARCHAR PRIMARY KEY, event_date DATE NOT NULL,
          service_id VARCHAR NOT NULL, payer VARCHAR NOT NULL, token VARCHAR NOT NULL,
          amount_atomic DECIMAL(38,0) NOT NULL CHECK(amount_atomic > 0),
          synthetic BOOLEAN NOT NULL,
          client_fingerprint VARCHAR,
          interface_status VARCHAR NOT NULL DEFAULT 'absent');
        CREATE TABLE raw.service_labels (
          assertion_id VARCHAR PRIMARY KEY, service_id VARCHAR NOT NULL,
          category VARCHAR NOT NULL, valid_from DATE NOT NULL, valid_to DATE,
          recorded_at TIMESTAMPTZ NOT NULL, evidence_level VARCHAR NOT NULL, source VARCHAR NOT NULL);
        CREATE TABLE raw.label_changes (
          assertion_id VARCHAR PRIMARY KEY, payload VARCHAR NOT NULL,
          start_date DATE NOT NULL, end_date DATE NOT NULL,
          status VARCHAR NOT NULL CHECK(status IN ('pending','applied')), publication_id VARCHAR);
        CREATE TABLE raw.calendar (event_date DATE PRIMARY KEY);
    """)
