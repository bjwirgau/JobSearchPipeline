SET @add_cover_letter_file_name = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'job_prospects'
          AND column_name = 'cover_letter_file_name'
    ),
    'SELECT 1',
    CONCAT(
        'ALTER TABLE job_prospects ',
        'ADD COLUMN cover_letter_file_name VARCHAR(255) NULL, ',
        'ADD KEY idx_job_prospects_cover_letter_pending ',
        '(resume_generation_candidate, cover_letter_file_name, updated_at, `match`)'
    )
);

PREPARE add_cover_letter_file_name FROM @add_cover_letter_file_name;
EXECUTE add_cover_letter_file_name;
DEALLOCATE PREPARE add_cover_letter_file_name;
