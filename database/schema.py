"""Current MySQL schema for the job-agent foundation."""

from __future__ import annotations

from utils.dates import to_utc_naive, utc_now

from .connection import Database, MySQLCursor


SCHEMA_VERSION = 3

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
        PRIMARY KEY (job_id),
        KEY idx_job_prospects_match (`match`),
        CONSTRAINT ck_job_prospects_match
            CHECK (`match` IS NULL OR (`match` >= 0 AND `match` <= 1))
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
        if current_version < SCHEMA_VERSION:
            _remove_legacy_tables(database, cursor)
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
