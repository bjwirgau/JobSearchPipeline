SET @add_job_prospect_payload = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'job_data'
    ),
    'SELECT 1',
    'ALTER TABLE job_prospects ADD COLUMN job_data JSON NULL'
);
PREPARE add_job_prospect_payload FROM @add_job_prospect_payload;
EXECUTE add_job_prospect_payload;
DEALLOCATE PREPARE add_job_prospect_payload;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (7, UTC_TIMESTAMP(6));
