SET @add_resume_file_name = IF(
    (
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'resume_file_name'
    ) = 0,
    CONCAT(
        'ALTER TABLE job_prospects ',
        'ADD COLUMN resume_file_name VARCHAR(255) NULL, ',
        'ADD KEY idx_job_prospects_resume_pending ',
        '(resume_generation_candidate, resume_file_name, updated_at, `match`)'
    ),
    'SELECT 1'
);

PREPARE add_resume_file_name FROM @add_resume_file_name;
EXECUTE add_resume_file_name;
DEALLOCATE PREPARE add_resume_file_name;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (13, UTC_TIMESTAMP(6));
