"""Small in-memory MySQL connector fake used by repository unit tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any


class FakeMySQLServer:
    """Persist committed rows across short-lived fake connector connections."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[object, dict[str, Any]]] = {
            "schema_migrations": {},
            "candidates": {},
            "resume_knowledge": {},
            "jobs": {},
            "applications": {},
            "workflow_runs": {},
        }
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
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self, *, dictionary: bool = False) -> "FakeMySQLCursor":
        return FakeMySQLCursor(self, dictionary=dictionary)

    def commit(self) -> None:
        self._server.tables = deepcopy(self.tables)
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
        if statement.startswith("insert ignore into schema_migrations"):
            version, applied_at = values
            self._connection.tables["schema_migrations"].setdefault(
                version,
                {"version": version, "applied_at": applied_at},
            )
            self.rowcount = 1
            return
        if statement.startswith("insert into candidates"):
            candidate_id, full_name, email, payload_json, updated_at = values
            self._connection.tables["candidates"][candidate_id] = {
                "candidate_id": candidate_id,
                "full_name": full_name,
                "email": email,
                "payload_json": payload_json,
                "updated_at": updated_at,
            }
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
        if statement.startswith("insert into jobs"):
            (
                job_id,
                source,
                external_id,
                deduplication_key,
                title,
                company,
                payload_json,
                discovered_at,
                updated_at,
            ) = values
            existing = self._connection.tables["jobs"].get(job_id)
            self._connection.tables["jobs"][job_id] = {
                "job_id": job_id,
                "source": source,
                "external_id": external_id,
                "deduplication_key": deduplication_key,
                "title": title,
                "company": company,
                "payload_json": payload_json,
                "discovered_at": (
                    existing["discovered_at"] if existing else discovered_at
                ),
                "updated_at": updated_at,
            }
            self.rowcount = 1
            return
        if statement.startswith("insert into applications"):
            (
                application_id,
                candidate_id,
                job_id,
                status,
                payload_json,
                updated_at,
            ) = values
            self._connection.tables["applications"][application_id] = {
                "application_id": application_id,
                "candidate_id": candidate_id,
                "job_id": job_id,
                "status": status,
                "payload_json": payload_json,
                "updated_at": updated_at,
            }
            self.rowcount = 1
            return
        if statement.startswith("select payload_json from candidates"):
            self._select_by_id("candidates", values[0])
            return
        if statement.startswith("select payload_json from resume_knowledge"):
            self._select_by_id("resume_knowledge", values[0])
            return
        if statement.startswith("select payload_json from jobs where job_id"):
            self._select_by_id("jobs", values[0])
            return
        if statement.startswith("select payload_json from jobs order by"):
            limit = int(values[0])
            rows = sorted(
                self._connection.tables["jobs"].values(),
                key=lambda row: _timestamp(row["discovered_at"]),
                reverse=True,
            )[:limit]
            self._rows = [{"payload_json": row["payload_json"]} for row in rows]
            return
        if statement.startswith("select payload_json from applications where application_id"):
            self._select_by_id("applications", values[0])
            return
        if statement.startswith("select payload_json from applications where status"):
            status = values[0]
            rows = sorted(
                (
                    row
                    for row in self._connection.tables["applications"].values()
                    if row["status"] == status
                ),
                key=lambda row: _timestamp(row["updated_at"]),
                reverse=True,
            )
            self._rows = [{"payload_json": row["payload_json"]} for row in rows]
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

    def _select_by_id(self, table: str, row_id: object) -> None:
        row = self._connection.tables[table].get(row_id)
        self._rows = [{"payload_json": row["payload_json"]}] if row else []


def _timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("fake MySQL timestamp must be a datetime")
    return value
