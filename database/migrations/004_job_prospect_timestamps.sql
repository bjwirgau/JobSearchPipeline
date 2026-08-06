SET @add_job_prospect_created_at = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'created_at'
    ),
    'SELECT 1',
    CONCAT(
        'ALTER TABLE job_prospects ADD COLUMN created_at DATETIME(6) ',
        'NOT NULL DEFAULT CURRENT_TIMESTAMP(6)'
    )
);
PREPARE add_job_prospect_created_at FROM @add_job_prospect_created_at;
EXECUTE add_job_prospect_created_at;
DEALLOCATE PREPARE add_job_prospect_created_at;

SET @add_job_prospect_updated_at = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'updated_at'
    ),
    'SELECT 1',
    CONCAT(
        'ALTER TABLE job_prospects ADD COLUMN updated_at DATETIME(6) ',
        'NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ',
        'ON UPDATE CURRENT_TIMESTAMP(6)'
    )
);
PREPARE add_job_prospect_updated_at FROM @add_job_prospect_updated_at;
EXECUTE add_job_prospect_updated_at;
DEALLOCATE PREPARE add_job_prospect_updated_at;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (4, UTC_TIMESTAMP(6));
