-- Replace numeric hypothesis scores with categorical bands.
-- Existing hypothesis rows are disposable (dev/test only).
DROP TABLE IF EXISTS hypotheses;
CREATE TABLE hypotheses (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    iq_id VARCHAR NOT NULL,
    statement TEXT NOT NULL,
    likelihood VARCHAR NOT NULL,
    confidence VARCHAR NOT NULL,
    supporting_claim_ids JSON NOT NULL,
    contradicting_claim_ids JSON,
    gaps JSON NOT NULL,
    gap_assessments JSON NOT NULL,
    next_evidence_requests JSON NOT NULL,
    status VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hypotheses_iq ON hypotheses(iq_id);
CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status);

INSERT INTO schema_migrations (version, description, applied_at)
VALUES (2, 'Replace numeric hypothesis scores with categorical bands', CURRENT_TIMESTAMP);
