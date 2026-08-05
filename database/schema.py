"""Current MySQL schema for the job-agent foundation."""

from __future__ import annotations

from utils.dates import to_utc_naive, utc_now

from .connection import Database


SCHEMA_VERSION = 2

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INT UNSIGNED NOT NULL PRIMARY KEY,
        applied_at DATETIME(6) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS candidates (
        candidate_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        email VARCHAR(320) NOT NULL,
        payload_json JSON NOT NULL,
        updated_at DATETIME(6) NOT NULL,
        PRIMARY KEY (candidate_id)
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_knowledge (
        candidate_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        schema_version INT UNSIGNED NOT NULL,
        payload_json JSON NOT NULL,
        updated_at DATETIME(6) NOT NULL,
        PRIMARY KEY (candidate_id),
        CONSTRAINT fk_resume_knowledge_candidate
            FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id CHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        source VARCHAR(64) NOT NULL,
        external_id VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        deduplication_key CHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        title VARCHAR(255) NOT NULL,
        company VARCHAR(255) NOT NULL,
        payload_json JSON NOT NULL,
        discovered_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NOT NULL,
        PRIMARY KEY (job_id),
        UNIQUE KEY uq_jobs_source_external_id (source, external_id),
        KEY idx_jobs_deduplication_key (deduplication_key),
        KEY idx_jobs_company_title (company, title)
    ) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS applications (
        application_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        candidate_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        job_id CHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        status VARCHAR(32) NOT NULL,
        payload_json JSON NOT NULL,
        updated_at DATETIME(6) NOT NULL,
        PRIMARY KEY (application_id),
        KEY idx_applications_status (status),
        KEY idx_applications_candidate_id (candidate_id),
        KEY idx_applications_job_id (job_id),
        CONSTRAINT fk_applications_candidate
            FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id),
        CONSTRAINT fk_applications_job
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
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
    with database.cursor(dictionary=False) as cursor:
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        cursor.execute(
            """
            INSERT IGNORE INTO schema_migrations(version, applied_at)
            VALUES (%s, %s)
            """,
            (SCHEMA_VERSION, to_utc_naive(utc_now())),
        )
