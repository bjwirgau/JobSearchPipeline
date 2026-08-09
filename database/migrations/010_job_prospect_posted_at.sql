SET @add_job_prospect_posted_at = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'posted_at'
    ),
    'SELECT 1',
    CONCAT(
        'ALTER TABLE job_prospects ',
        'ADD COLUMN posted_at DATETIME(6) NULL'
    )
);
PREPARE add_job_prospect_posted_at FROM @add_job_prospect_posted_at;
EXECUTE add_job_prospect_posted_at;
DEALLOCATE PREPARE add_job_prospect_posted_at;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (10, UTC_TIMESTAMP(6));
