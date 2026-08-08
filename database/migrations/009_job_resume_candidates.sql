SET @add_resume_generation_candidate = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'resume_generation_candidate'
    ),
    'SELECT 1',
    CONCAT(
        'ALTER TABLE job_prospects ',
        'ADD COLUMN resume_generation_candidate BOOLEAN NOT NULL DEFAULT FALSE, ',
        'ADD KEY idx_job_prospects_resume_candidate ',
        '(resume_generation_candidate, `match`)'
    )
);
PREPARE add_resume_generation_candidate FROM @add_resume_generation_candidate;
EXECUTE add_resume_generation_candidate;
DEALLOCATE PREPARE add_resume_generation_candidate;

SET @add_resume_generation_model = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'resume_generation_model'
    ),
    'SELECT 1',
    CONCAT(
        'ALTER TABLE job_prospects ',
        'ADD COLUMN resume_generation_model VARCHAR(64) NULL'
    )
);
PREPARE add_resume_generation_model FROM @add_resume_generation_model;
EXECUTE add_resume_generation_model;
DEALLOCATE PREPARE add_resume_generation_model;

UPDATE job_prospects
SET resume_generation_candidate = TRUE,
    resume_generation_model = 'gpt-5.4'
WHERE `match` > 0.85
  AND resume_generation_candidate = FALSE;

UPDATE job_prospects
SET resume_generation_model = 'gpt-5.4'
WHERE resume_generation_candidate = TRUE
  AND resume_generation_model IS NULL;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (9, UTC_TIMESTAMP(6));
