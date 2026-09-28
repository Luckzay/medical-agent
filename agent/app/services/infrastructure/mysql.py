from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pymysql  # type: ignore[import-untyped]
from pymysql.connections import Connection  # type: ignore[import-untyped]

from app.core.config import Settings, get_settings


class MySQLDatabase:
    """Small connection factory for short, thread-safe MySQL transactions."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def connect(self) -> Connection:
        password = self.settings.mysql_password
        return pymysql.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=password.get_secret_value() if password else "",
            database=self.settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            connect_timeout=self.settings.mysql_connect_timeout_seconds,
            read_timeout=self.settings.mysql_read_timeout_seconds,
            write_timeout=self.settings.mysql_write_timeout_seconds,
        )

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        connection = self.connect()
        try:
            connection.begin()
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def cursor(self) -> Iterator[Any]:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                yield cursor

    def ping(self) -> None:
        connection = self.connect()
        try:
            connection.ping(reconnect=False)
        finally:
            connection.close()
