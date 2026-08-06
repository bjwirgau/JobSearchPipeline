SET @drop_resume_candidate_fk = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_schema = DATABASE()
          AND table_name = 'resume_knowledge'
          AND constraint_name = 'fk_resume_knowledge_candidate'
          AND constraint_type = 'FOREIGN KEY'
    ),
    'ALTER TABLE resume_knowledge DROP FOREIGN KEY fk_resume_knowledge_candidate',
    'SELECT 1'
);
PREPARE drop_resume_candidate_fk FROM @drop_resume_candidate_fk;
EXECUTE drop_resume_candidate_fk;
DEALLOCATE PREPARE drop_resume_candidate_fk;

DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS candidates;

CREATE TABLE IF NOT EXISTS job_prospects (
    job_id CHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `match` DECIMAL(5, 4) NULL,
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    location VARCHAR(255) NOT NULL,
    salary VARCHAR(128) NOT NULL,
    source VARCHAR(64) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    PRIMARY KEY (job_id),
    KEY idx_job_prospects_match (`match`),
    CONSTRAINT ck_job_prospects_match
        CHECK (`match` IS NULL OR (`match` >= 0 AND `match` <= 1))
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (3, UTC_TIMESTAMP(6));
