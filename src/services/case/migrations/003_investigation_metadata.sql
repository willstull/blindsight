-- Add investigation metadata column to cases table.
-- Stores scenario context, focal principals, rationale, etc.
ALTER TABLE cases ADD COLUMN investigation_metadata JSON;

INSERT INTO schema_migrations (version, description, applied_at)
VALUES (3, 'Add investigation_metadata column to cases', CURRENT_TIMESTAMP);
