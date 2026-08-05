"""MySQL connection and schema helpers."""

from .connection import Database, MissingMySQLDependencyError, MySQLConfig
from .schema import SCHEMA_VERSION, initialize_schema

__all__ = [
    "Database",
    "MissingMySQLDependencyError",
    "MySQLConfig",
    "SCHEMA_VERSION",
    "initialize_schema",
]
