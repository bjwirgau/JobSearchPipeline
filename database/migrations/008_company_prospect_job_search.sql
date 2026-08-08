SET @add_company_prospect_job_search = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'company_prospects'
          AND column_name = 'last_job_search_at'
    ),
    'SELECT 1',
    CONCAT(
        'ALTER TABLE company_prospects ',
        'ADD COLUMN last_job_search_at DATETIME(6) NULL, ',
        'ADD KEY idx_company_prospects_job_search (last_job_search_at)'
    )
);
PREPARE add_company_prospect_job_search FROM @add_company_prospect_job_search;
EXECUTE add_company_prospect_job_search;
DEALLOCATE PREPARE add_company_prospect_job_search;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (8, UTC_TIMESTAMP(6));
