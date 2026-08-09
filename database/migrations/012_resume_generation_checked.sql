SET @add_resume_generation_checked = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'resume_generation_checked'
    ),
    'SELECT 1',
    CONCAT(
        'ALTER TABLE job_prospects ',
        'ADD COLUMN resume_generation_checked BOOLEAN NOT NULL DEFAULT FALSE, ',
        'ADD KEY idx_job_prospects_resume_unchecked ',
        '(resume_generation_checked, created_at, job_id)'
    )
);
PREPARE add_resume_generation_checked FROM @add_resume_generation_checked;
EXECUTE add_resume_generation_checked;
DEALLOCATE PREPARE add_resume_generation_checked;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (12, UTC_TIMESTAMP(6));
