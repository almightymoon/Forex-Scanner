"""Database configuration."""

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = "postgresql://fxnav:fxnav_dev@localhost:5432/fxnavigators"
    sqlite_path: str = "data/scanner.db"
    pool_size: int = 5
    prefer_postgres: bool = True


@lru_cache
def get_database_config() -> DatabaseConfig:
    return DatabaseConfig(
        url=os.getenv(
            "DATABASE_URL",
            "postgresql://fxnav:fxnav_dev@localhost:5432/fxnavigators",
        ),
        sqlite_path=os.getenv("SQLITE_PATH", "data/scanner.db"),
        prefer_postgres=os.getenv("PREFER_POSTGRES", "true").lower() == "true",
    )
