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
        self.company_prospect_columns: set[str] = set()
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
        self.company_prospect_columns = set(server.company_prospect_columns)
        self.resume_candidate_foreign_key = server.resume_candidate_foreign_key
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self, *, dictionary: bool = False) -> "FakeMySQLCursor":
        return FakeMySQLCursor(self, dictionary=dictionary)

    def commit(self) -> None:
        self._server.tables = deepcopy(self.tables)
        self._server.job_prospect_columns = set(self.job_prospect_columns)
        self._server.company_prospect_columns = set(self.company_prospect_columns)
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
                        "posted_at",
                        "job_data",
                        "resume_generation_candidate",
                        "resume_generation_model",
                        "created_at",
                        "updated_at",
                    }
            if " company_prospects " in statement:
                self._connection.tables.setdefault("company_prospects", {})
                if not self._connection.company_prospect_columns:
                    self._connection.company_prospect_columns = {
                        "company_id",
                        "company_name",
                        "board_token",
                        "company_url",
                        "last_job_search_at",
                        "created_at",
                        "updated_at",
                    }
            if " crawl_pages " in statement:
                self._connection.tables.setdefault("crawl_pages", {})
            if " crawl_discovery_cursors " in statement:
                self._connection.tables.setdefault(
                    "crawl_discovery_cursors",
                    {},
                )
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
            available_columns = self._connection.job_prospect_columns
            if "column_name = 'job_data'" in statement:
                requested_columns = {"job_data"}
            elif "column_name = 'posted_at'" in statement:
                requested_columns = {"posted_at"}
            elif "'resume_generation_candidate'" in statement:
                requested_columns = {
                    "resume_generation_candidate",
                    "resume_generation_model",
                }
            elif "column_name = 'last_job_search_at'" in statement:
                requested_columns = {"last_job_search_at"}
                available_columns = self._connection.company_prospect_columns
            self._rows = [
                {"app_column_name": column_name}
                for column_name in sorted(
                    available_columns & requested_columns
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
            if "add column posted_at" in statement:
                self._connection.job_prospect_columns.add("posted_at")
                for row in self._connection.tables["job_prospects"].values():
                    row["posted_at"] = None
            if "add column resume_generation_candidate" in statement:
                self._connection.job_prospect_columns.add(
                    "resume_generation_candidate"
                )
                for row in self._connection.tables["job_prospects"].values():
                    row["resume_generation_candidate"] = False
            if "add column resume_generation_model" in statement:
                self._connection.job_prospect_columns.add(
                    "resume_generation_model"
                )
                for row in self._connection.tables["job_prospects"].values():
                    row["resume_generation_model"] = None
            return
        if statement.startswith("alter table company_prospects"):
            if "add column last_job_search_at" in statement:
                self._connection.company_prospect_columns.add(
                    "last_job_search_at"
                )
                for row in self._connection.tables["company_prospects"].values():
                    row["last_job_search_at"] = None
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
                posted_at,
                job_data,
                resume_generation_candidate,
                resume_generation_model,
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
                "posted_at": (
                    posted_at
                    if posted_at is not None
                    else existing.get("posted_at") if existing else None
                ),
                "job_data": (
                    existing.get("job_data")
                    if existing
                    and existing.get("posted_at") is not None
                    and posted_at is None
                    and "when incoming.posted_at is null" in statement
                    else job_data
                    if job_data is not None
                    else existing.get("job_data") if existing else None
                ),
                "resume_generation_candidate": (
                    resume_generation_candidate
                    if existing is None
                    or "resume_generation_candidate = incoming" in statement
                    else existing.get("resume_generation_candidate", False)
                ),
                "resume_generation_model": (
                    resume_generation_model
                    if existing is None
                    or "resume_generation_model = incoming" in statement
                    else existing.get("resume_generation_model")
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
                "last_job_search_at": (
                    existing.get("last_job_search_at") if existing else None
                ),
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
        if statement.startswith("insert into crawl_discovery_cursors"):
            provider, scope_key, next_page, page_count = values
            key = (provider, scope_key)
            existing = self._connection.tables["crawl_discovery_cursors"].get(
                key
            )
            now = to_utc_naive(utc_now())
            self._connection.tables["crawl_discovery_cursors"][key] = {
                "provider": provider,
                "scope_key": scope_key,
                "next_page": next_page,
                "page_count": page_count,
                "created_at": existing["created_at"] if existing else now,
                "updated_at": now,
            }
            self.rowcount = 1
            return
        if statement.startswith("update job_prospects"):
            if "where `match` >" in statement:
                model, threshold = values
                for row in self._connection.tables["job_prospects"].values():
                    if (
                        row.get("match") is not None
                        and row["match"] > threshold
                        and not row.get("resume_generation_candidate", False)
                    ):
                        row["resume_generation_candidate"] = True
                        row["resume_generation_model"] = model
                        self.rowcount += 1
                return
            if "where resume_generation_candidate = true" in statement:
                (model,) = values
                for row in self._connection.tables["job_prospects"].values():
                    if (
                        row.get("resume_generation_candidate", False)
                        and row.get("resume_generation_model") is None
                    ):
                        row["resume_generation_model"] = model
                        self.rowcount += 1
                return
            match, resume_candidate, resume_model, job_id = values
            row = self._connection.tables["job_prospects"].get(job_id)
            if row:
                row["match"] = match
                row["resume_generation_candidate"] = resume_candidate
                row["resume_generation_model"] = resume_model
                row["updated_at"] = to_utc_naive(utc_now())
                self.rowcount = 1
            return
        if statement.startswith("update company_prospects"):
            selected_at, *company_ids = values
            for company_id in company_ids:
                row = self._connection.tables["company_prospects"].get(company_id)
                if row:
                    row["last_job_search_at"] = selected_at
                    row["updated_at"] = to_utc_naive(utc_now())
                    self.rowcount += 1
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
            if "where resume_generation_candidate = true" in statement:
                limit = int(values[0])
                rows = sorted(
                    (
                        row
                        for row in self._connection.tables[
                            "job_prospects"
                        ].values()
                        if row.get("resume_generation_candidate", False)
                    ),
                    key=lambda row: (
                        -(row["match"] or 0),
                        row["title"],
                        row["company"],
                    ),
                )[:limit]
                self._rows = [dict(row) for row in rows]
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
            candidates = tuple(
                row
                for row in self._connection.tables["company_prospects"].values()
                if "company_url like" not in statement
                or row["company_url"].startswith(
                    "https://job-boards.greenhouse.io/"
                )
            )
            if "order by (last_job_search_at is not null)" in statement:
                rows = sorted(
                    candidates,
                    key=lambda row: (
                        row.get("last_job_search_at") is not None,
                        row.get("last_job_search_at"),
                        row["company_name"],
                        row["board_token"],
                    ),
                )
            else:
                rows = sorted(
                    candidates,
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
            source, page_type, *remaining = values
            rows = [
                row
                for row in self._connection.tables["crawl_pages"].values()
                if row["source"] == source and row["page_type"] == page_type
            ]
            if remaining:
                as_of = remaining[0]
                rows = [row for row in rows if row["next_crawl_at"] > as_of]
                self._rows = [{"page_url": row["page_url"]} for row in rows]
            else:
                self._rows = [
                    dict(row) for row in sorted(rows, key=lambda row: row["page_url"])
                ]
            return
        if statement.startswith("select provider") and "from crawl_discovery_cursors" in statement:
            row = self._connection.tables["crawl_discovery_cursors"].get(
                (values[0], values[1])
            )
            self._rows = [dict(row)] if row else []
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
