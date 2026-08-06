"""Small in-memory MySQL connector fake used by repository unit tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class FakeMySQLServer:
    """Persist committed rows across short-lived fake connector connections."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[object, dict[str, Any]]] = {
            "schema_migrations": {
                2: {"version": 2, "applied_at": None},
            },
            "candidates": {},
            "resume_knowledge": {},
            "jobs": {},
            "applications": {},
            "job_prospects": {},
            "workflow_runs": {},
        }
        self.resume_candidate_foreign_key = True
        self.connect_calls: list[dict[str, object]] = []
        self.connections: list[FakeMySQLConnection] = []

    def connect(self, **arguments: object) -> "FakeMySQLConnection":
        self.connect_calls.append(arguments)
        connection = FakeMySQLConnection(self)
        self.connections.append(connection)
        return connection


class FakeMySQLConnection:
    def __init__(self, server: FakeMySQLServer) -> None:
        self._server = server
        self.tables = deepcopy(server.tables)
        self.resume_candidate_foreign_key = server.resume_candidate_foreign_key
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self, *, dictionary: bool = False) -> "FakeMySQLCursor":
        return FakeMySQLCursor(self, dictionary=dictionary)

    def commit(self) -> None:
        self._server.tables = deepcopy(self.tables)
        self._server.resume_candidate_foreign_key = (
            self.resume_candidate_foreign_key
        )
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class FakeMySQLCursor:
    def __init__(
        self,
        connection: FakeMySQLConnection,
        *,
        dictionary: bool,
    ) -> None:
        self._connection = connection
        self.dictionary = dictionary
        self.rowcount = 0
        self.closed = False
        self._rows: list[dict[str, Any]] = []

    def execute(
        self,
        operation: str,
        params: tuple[object, ...] | None = None,
    ) -> None:
        statement = " ".join(operation.split()).casefold()
        values = params or ()
        self.rowcount = 0
        self._rows = []

        if statement.startswith("create table if not exists"):
            return
        if statement.startswith("select coalesce(max(version)"):
            versions = self._connection.tables["schema_migrations"]
            self._rows = [{"version": max(versions, default=0)}]
            return
        if statement.startswith("select count(*) as constraint_count"):
            self._rows = [
                {
                    "constraint_count": int(
                        self._connection.resume_candidate_foreign_key
                    )
                }
            ]
            return
        if statement.startswith("alter table resume_knowledge"):
            self._connection.resume_candidate_foreign_key = False
            return
        if statement.startswith("drop table if exists"):
            table_name = statement.rsplit(" ", 1)[-1]
            self._connection.tables.pop(table_name, None)
            return
        if statement.startswith("insert ignore into schema_migrations"):
            version, applied_at = values
            self._connection.tables["schema_migrations"].setdefault(
                version,
                {"version": version, "applied_at": applied_at},
            )
            self.rowcount = 1
            return
        if statement.startswith("insert into resume_knowledge"):
            candidate_id, schema_version, payload_json, updated_at = values
            self._connection.tables["resume_knowledge"][candidate_id] = {
                "candidate_id": candidate_id,
                "schema_version": schema_version,
                "payload_json": payload_json,
                "updated_at": updated_at,
            }
            self.rowcount = 1
            return
        if statement.startswith("insert into job_prospects"):
            (
                job_id,
                match,
                title,
                company,
                location,
                salary,
                source,
                url,
            ) = values
            existing = self._connection.tables["job_prospects"].get(job_id)
            self._connection.tables["job_prospects"][job_id] = {
                "job_id": job_id,
                "match": (
                    match
                    if match is not None
                    else existing["match"] if existing else None
                ),
                "title": title,
                "company": company,
                "location": location,
                "salary": salary,
                "source": source,
                "url": url,
            }
            self.rowcount = 1
            return
        if statement.startswith("update job_prospects"):
            match, job_id = values
            row = self._connection.tables["job_prospects"].get(job_id)
            if row:
                row["match"] = match
                self.rowcount = 1
            return
        if statement.startswith("select job_id") and "from job_prospects" in statement:
            if "where job_id" in statement:
                row = self._connection.tables["job_prospects"].get(values[0])
                self._rows = [dict(row)] if row else []
                return
            limit = int(values[0])
            rows = sorted(
                self._connection.tables["job_prospects"].values(),
                key=lambda row: (
                    row["match"] is None,
                    -(row["match"] or 0),
                    row["title"],
                    row["company"],
                ),
            )[:limit]
            self._rows = [dict(row) for row in rows]
            return
        if statement.startswith("select payload_json from resume_knowledge"):
            self._select_payload("resume_knowledge", values[0])
            return
        if statement.startswith("delete from resume_knowledge"):
            candidate_id = values[0]
            self.rowcount = int(
                self._connection.tables["resume_knowledge"].pop(
                    candidate_id,
                    None,
                )
                is not None
            )
            return

        raise AssertionError(f"unsupported SQL in fake MySQL connector: {statement}")

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def close(self) -> None:
        self.closed = True

    def _select_payload(self, table: str, row_id: object) -> None:
        row = self._connection.tables[table].get(row_id)
        self._rows = [{"payload_json": row["payload_json"]}] if row else []
