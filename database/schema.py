"""Current MySQL schema for the job-agent foundation."""

from __future__ import annotations

from models import (
    DEFAULT_RESUME_CANDIDATE_THRESHOLD,
    DEFAULT_RESUME_GENERATION_MODEL,
)
from utils.dates import to_utc_naive, utc_now

from .connection import Database, MySQLCursor


SCHEMA_VERSION = 14

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
        posted_at DATETIME(6) NULL,
        job_data JSON NULL,
        resume_generation_checked BOOLEAN NOT NULL DEFAULT FALSE,
        resume_generation_candidate BOOLEAN NOT NULL DEFAULT FALSE,
        resume_generation_model VARCHAR(64) NULL,
        resume_file_name VARCHAR(255) NULL,
        cover_letter_file_name VARCHAR(255) NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (job_id),
        KEY idx_job_prospects_match (`match`),
        KEY idx_job_prospects_resume_candidate (
            resume_generation_candidate, `match`
        ),
        KEY idx_job_prospects_resume_unchecked (
            resume_generation_checked, created_at, job_id
        ),
        KEY idx_job_prospects_resume_pending (
            resume_generation_candidate, resume_file_name, updated_at, `match`
        ),
        KEY idx_job_prospects_cover_letter_pending (
            resume_generation_candidate, cover_letter_file_name, updated_at, `match`
        ),
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
        last_job_search_at DATETIME(6) NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (company_id),
        UNIQUE KEY uq_company_prospects_url (company_url),
        KEY idx_company_prospects_board_token (board_token),
        KEY idx_company_prospects_job_search (last_job_search_at)
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
        if current_version < 8:
            _add_company_prospect_job_search_timestamp(database, cursor)
        if current_version < 9:
            _add_job_prospect_resume_generation(database, cursor)
        if current_version < 10:
            _add_job_prospect_posted_at(database, cursor)
        if current_version < 12:
            _add_job_prospect_resume_generation_checked(database, cursor)
        if current_version < 13:
            _add_job_prospect_resume_file_name(database, cursor)
        if current_version < 14:
            _add_job_prospect_cover_letter_file_name(database, cursor)
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


def _add_company_prospect_job_search_timestamp(
    database: Database,
    cursor: MySQLCursor,
) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS app_column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'company_prospects'
          AND column_name = 'last_job_search_at'
        """,
        (database.config.database,),
    )
    if not cursor.fetchone():
        cursor.execute(
            """
            ALTER TABLE company_prospects
            ADD COLUMN last_job_search_at DATETIME(6) NULL,
            ADD KEY idx_company_prospects_job_search (last_job_search_at)
            """
        )


def _add_job_prospect_resume_generation(
    database: Database,
    cursor: MySQLCursor,
) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS app_column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'job_prospects'
          AND column_name IN (
              'resume_generation_candidate',
              'resume_generation_model'
          )
        """,
        (database.config.database,),
    )
    existing = {str(row["app_column_name"]) for row in cursor.fetchall()}
    additions: list[str] = []
    if "resume_generation_candidate" not in existing:
        additions.extend(
            (
                "ADD COLUMN resume_generation_candidate BOOLEAN NOT NULL "
                "DEFAULT FALSE",
                "ADD KEY idx_job_prospects_resume_candidate "
                "(resume_generation_candidate, `match`)",
            )
        )
    if "resume_generation_model" not in existing:
        additions.append("ADD COLUMN resume_generation_model VARCHAR(64) NULL")
    if additions:
        cursor.execute("ALTER TABLE job_prospects " + ", ".join(additions))
    cursor.execute(
        """
        UPDATE job_prospects
        SET resume_generation_candidate = TRUE,
            resume_generation_model = %s
        WHERE `match` > %s
          AND resume_generation_candidate = FALSE
        """,
        (
            DEFAULT_RESUME_GENERATION_MODEL,
            DEFAULT_RESUME_CANDIDATE_THRESHOLD,
        ),
    )
    cursor.execute(
        """
        UPDATE job_prospects
        SET resume_generation_model = %s
        WHERE resume_generation_candidate = TRUE
          AND resume_generation_model IS NULL
        """,
        (DEFAULT_RESUME_GENERATION_MODEL,),
    )


def _add_job_prospect_posted_at(
    database: Database,
    cursor: MySQLCursor,
) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS app_column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'job_prospects'
          AND column_name = 'posted_at'
        """,
        (database.config.database,),
    )
    if not cursor.fetchone():
        cursor.execute(
            "ALTER TABLE job_prospects ADD COLUMN posted_at DATETIME(6) NULL"
        )


def _add_job_prospect_resume_generation_checked(
    database: Database,
    cursor: MySQLCursor,
) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS app_column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'job_prospects'
          AND column_name = 'resume_generation_checked'
        """,
        (database.config.database,),
    )
    if not cursor.fetchone():
        cursor.execute(
            """
            ALTER TABLE job_prospects
            ADD COLUMN resume_generation_checked BOOLEAN NOT NULL DEFAULT FALSE,
            ADD KEY idx_job_prospects_resume_unchecked (
                resume_generation_checked, created_at, job_id
            )
            """
        )


def _add_job_prospect_resume_file_name(
    database: Database,
    cursor: MySQLCursor,
) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS app_column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'job_prospects'
          AND column_name = 'resume_file_name'
        """,
        (database.config.database,),
    )
    if not cursor.fetchone():
        cursor.execute(
            """
            ALTER TABLE job_prospects
            ADD COLUMN resume_file_name VARCHAR(255) NULL,
            ADD KEY idx_job_prospects_resume_pending (
                resume_generation_candidate, resume_file_name, updated_at, `match`
            )
            """
        )


def _add_job_prospect_cover_letter_file_name(
    database: Database,
    cursor: MySQLCursor,
) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS app_column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'job_prospects'
          AND column_name = 'cover_letter_file_name'
        """,
        (database.config.database,),
    )
    if not cursor.fetchone():
        cursor.execute(
            """
            ALTER TABLE job_prospects
            ADD COLUMN cover_letter_file_name VARCHAR(255) NULL,
            ADD KEY idx_job_prospects_cover_letter_pending (
                resume_generation_candidate, cover_letter_file_name,
                updated_at, `match`
            )
            """
        )
