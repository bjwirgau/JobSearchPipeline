CREATE TABLE IF NOT EXISTS resume_knowledge (
    candidate_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
);
