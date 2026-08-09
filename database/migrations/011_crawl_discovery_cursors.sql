CREATE TABLE IF NOT EXISTS crawl_discovery_cursors (
    provider VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    scope_key VARCHAR(512) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    next_page INT UNSIGNED NOT NULL,
    page_count INT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (provider, scope_key),
    CONSTRAINT ck_crawl_discovery_cursor_page
        CHECK (page_count > 0 AND next_page < page_count)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

INSERT IGNORE INTO schema_migrations(version, applied_at)
VALUES (11, UTC_TIMESTAMP(6));
