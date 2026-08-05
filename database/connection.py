"""Transactional MySQL connection management for persistence repositories."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol


class MissingMySQLDependencyError(RuntimeError):
    pass


class MySQLCursor(Protocol):
    rowcount: int

    def execute(
        self,
        operation: str,
        params: Sequence[object] | Mapping[str, object] | None = None,
    ) -> Any:
        """Execute one parameterized SQL statement."""

    def fetchone(self) -> Mapping[str, Any] | None:
        """Return one dictionary row, when available."""

    def fetchall(self) -> list[Mapping[str, Any]]:
        """Return all dictionary rows."""

    def close(self) -> None:
        """Release cursor resources."""


class MySQLConnection(Protocol):
    def cursor(self, *, dictionary: bool = False) -> MySQLCursor:
        """Create a cursor."""

    def commit(self) -> None:
        """Commit the current transaction."""

    def rollback(self) -> None:
        """Roll back the current transaction."""

    def close(self) -> None:
        """Release connection resources."""


@dataclass(frozen=True, slots=True)
class MySQLConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    database: str = "job_agent"
    user: str = "job_agent"
    password: str | None = field(default=None, repr=False)
    connection_timeout: int = 10

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("MySQL host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("MySQL port must be between 1 and 65535")
        if not self.database.strip():
            raise ValueError("MySQL database must not be empty")
        if not self.user.strip():
            raise ValueError("MySQL user must not be empty")
        if self.connection_timeout <= 0:
            raise ValueError("MySQL connection timeout must be greater than zero")


ConnectFactory = Callable[..., MySQLConnection]


class Database:
    """Open short MySQL transactions and expose dictionary cursors to repositories."""

    def __init__(
        self,
        config: MySQLConfig,
        *,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        self.config = config
        self._connect_factory = connect_factory

    @contextmanager
    def connect(self) -> Iterator[MySQLConnection]:
        connection = self._new_connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def cursor(self, *, dictionary: bool = True) -> Iterator[MySQLCursor]:
        with self.connect() as connection:
            cursor = connection.cursor(dictionary=dictionary)
            try:
                yield cursor
            finally:
                cursor.close()

    def _new_connection(self) -> MySQLConnection:
        connect_factory = self._connect_factory
        if connect_factory is None:
            try:
                import mysql.connector
            except ImportError as error:
                raise MissingMySQLDependencyError(
                    "install MySQL support with: pip install -e ."
                ) from error
            connect_factory = mysql.connector.connect

        arguments: dict[str, object] = {
            "host": self.config.host,
            "port": self.config.port,
            "database": self.config.database,
            "user": self.config.user,
            "connection_timeout": self.config.connection_timeout,
            "charset": "utf8mb4",
            "use_unicode": True,
            "autocommit": False,
            "time_zone": "+00:00",
        }
        if self.config.password is not None:
            arguments["password"] = self.config.password
        return connect_factory(**arguments)
