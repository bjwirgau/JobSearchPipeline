CREATE TABLE IF NOT EXISTS company_prospects (
    company_id CHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    board_token VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    company_url VARCHAR(512) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (company_id),
    UNIQUE KEY uq_company_prospects_url (company_url),
    KEY idx_company_prospects_board_token (board_token)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (5, UTC_TIMESTAMP(6));
