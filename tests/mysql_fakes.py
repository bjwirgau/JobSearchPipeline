"""Small in-memory MySQL connector fake used by repository unit tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from utils.dates import to_utc_naive, utc_now


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
            "workflow_runs": {},
        }
        self.job_prospect_columns: set[str] = set()
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
        self.job_prospect_columns = set(server.job_prospect_columns)
        self.resume_candidate_foreign_key = server.resume_candidate_foreign_key
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self, *, dictionary: bool = False) -> "FakeMySQLCursor":
        return FakeMySQLCursor(self, dictionary=dictionary)

    def commit(self) -> None:
        self._server.tables = deepcopy(self.tables)
        self._server.job_prospect_columns = set(self.job_prospect_columns)
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
            if " job_prospects " in statement:
                self._connection.tables.setdefault("job_prospects", {})
                if not self._connection.job_prospect_columns:
                    self._connection.job_prospect_columns = {
                        "job_id",
                        "match",
                        "title",
                        "company",
                        "location",
                        "salary",
                        "source",
                        "url",
                        "job_data",
                        "created_at",
                        "updated_at",
                    }
            if " company_prospects " in statement:
                self._connection.tables.setdefault("company_prospects", {})
            if " crawl_pages " in statement:
                self._connection.tables.setdefault("crawl_pages", {})
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
        if statement.startswith("select column_name as app_column_name"):
            requested_columns = {"created_at", "updated_at"}
            if "column_name = 'job_data'" in statement:
                requested_columns = {"job_data"}
            self._rows = [
                {"app_column_name": column_name}
                for column_name in sorted(
                    self._connection.job_prospect_columns
                    & requested_columns
                )
            ]
            return
        if statement.startswith("alter table resume_knowledge"):
            self._connection.resume_candidate_foreign_key = False
            return
        if statement.startswith("alter table job_prospects"):
            now = to_utc_naive(utc_now())
            for column_name in ("created_at", "updated_at"):
                if f"add column {column_name}" in statement:
                    self._connection.job_prospect_columns.add(column_name)
                    for row in self._connection.tables["job_prospects"].values():
                        row[column_name] = now
            if "add column job_data" in statement:
                self._connection.job_prospect_columns.add("job_data")
                for row in self._connection.tables["job_prospects"].values():
                    row["job_data"] = None
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
                job_data,
            ) = values
            existing = self._connection.tables["job_prospects"].get(job_id)
            now = to_utc_naive(utc_now())
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
                "job_data": (
                    job_data
                    if job_data is not None
                    else existing.get("job_data") if existing else None
                ),
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
            }
            self.rowcount = 1
            return
        if statement.startswith("insert into company_prospects"):
            company_id, company_name, board_token, company_url = values
            existing = self._connection.tables["company_prospects"].get(
                company_id
            )
            now = to_utc_naive(utc_now())
            self._connection.tables["company_prospects"][company_id] = {
                "company_id": company_id,
                "company_name": company_name,
                "board_token": board_token,
                "company_url": company_url,
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
            }
            self.rowcount = 1
            return
        if statement.startswith("insert into crawl_pages"):
            (
                page_url,
                source,
                page_type,
                crawl_status,
                last_crawled_at,
                next_crawl_at,
                last_error,
            ) = values
            existing = self._connection.tables["crawl_pages"].get(page_url)
            now = to_utc_naive(utc_now())
            self._connection.tables["crawl_pages"][page_url] = {
                "page_url": page_url,
                "source": source,
                "page_type": page_type,
                "crawl_status": crawl_status,
                "last_crawled_at": last_crawled_at,
                "next_crawl_at": next_crawl_at,
                "last_error": last_error,
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
            }
            self.rowcount = 1
            return
        if statement.startswith("update job_prospects"):
            match, job_id = values
            row = self._connection.tables["job_prospects"].get(job_id)
            if row:
                row["match"] = match
                row["updated_at"] = to_utc_naive(utc_now())
                self.rowcount = 1
            return
        if statement.startswith("select job_data") and "from job_prospects" in statement:
            limit = int(values[0])
            rows = sorted(
                (
                    row
                    for row in self._connection.tables["job_prospects"].values()
                    if row["match"] is None and row.get("job_data") is not None
                ),
                key=lambda row: (row["created_at"], row["job_id"]),
            )[:limit]
            self._rows = [{"job_data": row["job_data"]} for row in rows]
            return
        if statement.startswith("select job_id") and "from job_prospects" in statement:
            if "where job_id" in statement:
                row = self._connection.tables["job_prospects"].get(values[0])
                self._rows = [dict(row)] if row else []
                return
            if "where `match` is not null" in statement:
                selected_ids = set(values)
                self._rows = [
                    {"job_id": row["job_id"]}
                    for row in self._connection.tables["job_prospects"].values()
                    if row["job_id"] in selected_ids and row["match"] is not None
                ]
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
        if statement.startswith("select company_url from company_prospects"):
            self._rows = [
                {"company_url": row["company_url"]}
                for row in self._connection.tables["company_prospects"].values()
            ]
            return
        if statement.startswith("select company_id") and "from company_prospects" in statement:
            if "where company_id" in statement:
                row = self._connection.tables["company_prospects"].get(values[0])
                self._rows = [dict(row)] if row else []
                return
            rows = sorted(
                self._connection.tables["company_prospects"].values(),
                key=lambda row: (row["company_name"], row["board_token"]),
            )
            if values:
                rows = rows[: int(values[0])]
            self._rows = [dict(row) for row in rows]
            return
        if statement.startswith("select page_url") and "from crawl_pages" in statement:
            if "where page_url" in statement:
                row = self._connection.tables["crawl_pages"].get(values[0])
                self._rows = [dict(row)] if row else []
                return
            source, page_type, as_of = values
            self._rows = [
                {"page_url": row["page_url"]}
                for row in self._connection.tables["crawl_pages"].values()
                if row["source"] == source
                and row["page_type"] == page_type
                and row["next_crawl_at"] > as_of
            ]
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
