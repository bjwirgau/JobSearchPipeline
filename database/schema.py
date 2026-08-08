"""Current MySQL schema for the job-agent foundation."""

from __future__ import annotations

from utils.dates import to_utc_naive, utc_now

from .connection import Database, MySQLCursor


SCHEMA_VERSION = 7

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INT UNSIGNED NOT NULL PRIMARY KEY,
        applied_at DATETIME(6) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_knowledge (
        candidate_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        schema_version INT UNSIGNED NOT NULL,
        payload_json JSON NOT NULL,
        updated_at DATETIME(6) NOT NULL,
        PRIMARY KEY (candidate_id)
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS job_prospects (
        job_id CHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        `match` DECIMAL(5, 4) NULL,
        title VARCHAR(255) NOT NULL,
        company VARCHAR(255) NOT NULL,
        location VARCHAR(255) NOT NULL,
        salary VARCHAR(128) NOT NULL,
        source VARCHAR(64) NOT NULL,
        url VARCHAR(2048) NOT NULL,
        job_data JSON NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (job_id),
        KEY idx_job_prospects_match (`match`),
        CONSTRAINT ck_job_prospects_match
            CHECK (`match` IS NULL OR (`match` >= 0 AND `match` <= 1))
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
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
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
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
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS workflow_runs (
        run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        workflow_name VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        payload_json JSON NOT NULL,
        updated_at DATETIME(6) NOT NULL,
        PRIMARY KEY (run_id),
        KEY idx_workflow_runs_status (status)
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
)


def initialize_schema(database: Database) -> None:
    with database.cursor() as cursor:
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        cursor.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        )
        row = cursor.fetchone()
        current_version = int(row["version"]) if row else 0
        if current_version < 3:
            _remove_legacy_tables(database, cursor)
        if current_version < 4:
            _add_job_prospect_timestamps(database, cursor)
        if current_version < 7:
            _add_job_prospect_payload(database, cursor)
        cursor.execute(
            """
            INSERT IGNORE INTO schema_migrations(version, applied_at)
            VALUES (%s, %s)
            """,
            (SCHEMA_VERSION, to_utc_naive(utc_now())),
        )


def _remove_legacy_tables(database: Database, cursor: MySQLCursor) -> None:
    cursor.execute(
        """
        SELECT COUNT(*) AS constraint_count
        FROM information_schema.table_constraints
        WHERE constraint_schema = %s
          AND table_name = 'resume_knowledge'
          AND constraint_name = 'fk_resume_knowledge_candidate'
          AND constraint_type = 'FOREIGN KEY'
        """,
        (database.config.database,),
    )
    row = cursor.fetchone()
    if row and int(row["constraint_count"]) > 0:
        cursor.execute(
            """
            ALTER TABLE resume_knowledge
            DROP FOREIGN KEY fk_resume_knowledge_candidate
            """
        )
    for table_name in ("applications", "jobs", "candidates"):
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")


def _add_job_prospect_timestamps(
    database: Database,
    cursor: MySQLCursor,
) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS app_column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'job_prospects'
          AND column_name IN ('created_at', 'updated_at')
        """,
        (database.config.database,),
    )
    existing = {str(row["app_column_name"]) for row in cursor.fetchall()}
    additions: list[str] = []
    if "created_at" not in existing:
        additions.append(
            "ADD COLUMN created_at DATETIME(6) NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP(6)"
        )
    if "updated_at" not in existing:
        additions.append(
            "ADD COLUMN updated_at DATETIME(6) NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"
        )
    if additions:
        cursor.execute("ALTER TABLE job_prospects " + ", ".join(additions))


def _add_job_prospect_payload(
    database: Database,
    cursor: MySQLCursor,
) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS app_column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'job_prospects'
          AND column_name = 'job_data'
        """,
        (database.config.database,),
    )
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE job_prospects ADD COLUMN job_data JSON NULL")
