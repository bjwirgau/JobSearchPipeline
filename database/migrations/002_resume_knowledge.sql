CREATE TABLE IF NOT EXISTS resume_knowledge (
    candidate_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    schema_version INT UNSIGNED NOT NULL,
    payload_json JSON NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (candidate_id),
    CONSTRAINT fk_resume_knowledge_candidate
        FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
