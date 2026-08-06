CREATE TABLE IF NOT EXISTS crawl_pages (
    page_url VARCHAR(512) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    page_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    crawl_status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    last_crawled_at DATETIME(6) NOT NULL,
    next_crawl_at DATETIME(6) NOT NULL,
    last_error VARCHAR(1024) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (page_url),
    KEY idx_crawl_pages_due (source, page_type, next_crawl_at),
    CONSTRAINT ck_crawl_pages_status
        CHECK (crawl_status IN ('success', 'failed'))
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (6, UTC_TIMESTAMP(6));
