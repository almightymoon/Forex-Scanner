"""Database factory — PostgreSQL when available, SQLite fallback."""

import os

from shared.configs.settings import get_settings

settings = get_settings()
_db_instance = None


def get_database():
    global _db_instance
    if _db_instance is not None:
        return _db_instance

    use_postgres = os.getenv("USE_POSTGRES", "auto").lower()

    if use_postgres in ("true", "auto"):
        try:
            import psycopg2
            from shared.postgres_db import PostgresDatabase

            db = PostgresDatabase()
            db._connect().close()
            _db_instance = db
            print("[DB] Using PostgreSQL")
            return _db_instance
        except Exception as e:
            if use_postgres == "true":
                raise
            print(f"[DB] PostgreSQL unavailable ({e}), using SQLite")

    from shared.database import Database
    _db_instance = Database()
    print("[DB] Using SQLite")
    return _db_instance
