# ruff: noqa: CPY001, S101
"""Tests for filtering tables before SQLAlchemy metadata reflection."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.engine import reflection
from sqlalchemy.exc import OperationalError

from tap_mysql.client import MySQLConnector
from tap_mysql.tap import TapMySQL


class FakeCatalogEntry:
    """Minimal catalog entry returned by the mocked connector method."""

    def __init__(self, schema: str, table: str) -> None:
        """Initialize a fake catalog entry."""
        self.schema = schema
        self.table = table

    def to_dict(self) -> dict[str, str]:
        """Return a test catalog entry."""
        return {"schema": self.schema, "table": self.table}


class FakeInspector:
    """Record multi-reflection calls and return selected objects."""

    def __init__(self, schema_names: list[str]) -> None:
        """Initialize a recording inspector."""
        self.schema_names = schema_names
        self.calls: list[tuple[str, str, list[str] | None]] = []

    def get_schema_names(self) -> list[str]:
        """Return configured test schemas."""
        return self.schema_names

    def get_multi_pk_constraint(
        self,
        *,
        schema: str,
        filter_names: list[str] | None,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """Record primary-key reflection."""
        self.calls.append(("primary_keys", schema, filter_names))
        return {}

    def get_multi_indexes(
        self,
        *,
        schema: str,
        filter_names: list[str] | None,
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """Record index reflection."""
        self.calls.append(("indexes", schema, filter_names))
        return {}

    def get_multi_columns(
        self,
        *,
        schema: str,
        filter_names: list[str] | None,
        kind: reflection.ObjectKind,
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """Record column reflection and return only requested tables."""
        call_name = "views" if kind is reflection.ObjectKind.ANY_VIEW else "tables"
        self.calls.append((call_name, schema, filter_names))
        if kind is reflection.ObjectKind.ANY_VIEW:
            return {}
        names = filter_names or ["unfiltered_table"]
        return {(schema, name): [] for name in names}


def create_connector(config: dict[str, Any]) -> MySQLConnector:
    """Create a connector without opening a database connection."""
    return MySQLConnector(
        config={"is_vitess": False, **config},
        sqlalchemy_url="mysql+pymysql://unused",
    )


def fake_catalog_entry(*args: Any, **kwargs: Any) -> FakeCatalogEntry:
    """Return a minimal catalog entry from connector positional arguments."""
    del kwargs
    return FakeCatalogEntry(schema=args[2], table=args[3])


def test_filter_tables_is_applied_to_every_reflection_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only configured objects reach columns, primary-key, and index reflection."""
    connector = create_connector(
        {
            "filter_tables": [
                "selected_schema.selected_table",
                "other_schema.other_table",
            ],
        }
    )
    inspector = FakeInspector(["selected_schema", "other_schema", "unused_schema"])
    monkeypatch.setattr(sqlalchemy, "inspect", lambda _: inspector)
    connector._cached_engine = Mock()  # noqa: SLF001
    monkeypatch.setattr(
        connector,
        "discover_catalog_entry",
        Mock(side_effect=fake_catalog_entry),
    )

    entries = connector.discover_catalog_entries()

    assert entries == [
        {"schema": "selected_schema", "table": "selected_table"},
        {"schema": "other_schema", "table": "other_table"},
    ]
    assert inspector.calls == [
        ("primary_keys", "selected_schema", ["selected_table"]),
        ("indexes", "selected_schema", ["selected_table"]),
        ("tables", "selected_schema", ["selected_table"]),
        ("views", "selected_schema", ["selected_table"]),
        ("primary_keys", "other_schema", ["other_table"]),
        ("indexes", "other_schema", ["other_table"]),
        ("tables", "other_schema", ["other_table"]),
        ("views", "other_schema", ["other_table"]),
    ]


def test_unqualified_filter_table_applies_to_each_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unqualified name is reflected in every discovered schema."""
    connector = create_connector({"filter_tables": ["selected_table"]})
    inspector = FakeInspector(["schema_a", "schema_b"])
    monkeypatch.setattr(sqlalchemy, "inspect", lambda _: inspector)
    connector._cached_engine = Mock()  # noqa: SLF001
    monkeypatch.setattr(
        connector,
        "discover_catalog_entry",
        Mock(side_effect=fake_catalog_entry),
    )

    entries = connector.discover_catalog_entries(reflect_indices=False)

    assert entries == [
        {"schema": "schema_a", "table": "selected_table"},
        {"schema": "schema_b", "table": "selected_table"},
    ]
    assert all(call[2] == ["selected_table"] for call in inspector.calls)
    assert all(call[0] != "indexes" for call in inspector.calls)


def test_empty_filter_tables_preserves_unfiltered_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty filter retains the existing discover-all behavior."""
    connector = create_connector({"filter_tables": []})
    inspector = FakeInspector(["selected_schema"])
    monkeypatch.setattr(sqlalchemy, "inspect", lambda _: inspector)
    connector._cached_engine = Mock()  # noqa: SLF001
    monkeypatch.setattr(
        connector,
        "discover_catalog_entry",
        Mock(side_effect=fake_catalog_entry),
    )

    entries = connector.discover_catalog_entries()

    assert entries == [{"schema": "selected_schema", "table": "unfiltered_table"}]
    assert all(call[2] is None for call in inspector.calls)


def test_filter_tables_avoids_unselected_view_reflection() -> None:
    """A restricted unselected view must not reach metadata reflection."""
    root_url = "mysql+pymysql://root:password@127.0.0.1:3306/melty"
    limited_url = (
        "mysql+pymysql://filter_tables_reader:filter_tables_password"
        "@127.0.0.1:3306/melty"
    )
    root_engine = sqlalchemy.create_engine(root_url)

    with root_engine.begin() as connection:
        connection.execute(text("DROP VIEW IF EXISTS filter_tables_restricted_view"))
        connection.execute(text("DROP TABLE IF EXISTS filter_tables_selected"))
        connection.execute(text("DROP USER IF EXISTS 'filter_tables_reader'@'%'"))
        connection.execute(
            text("CREATE TABLE filter_tables_selected (id INT PRIMARY KEY)")
        )
        connection.execute(
            text(
                "CREATE VIEW filter_tables_restricted_view "
                "AS SELECT id FROM filter_tables_selected"
            )
        )
        connection.execute(
            text(
                "CREATE USER 'filter_tables_reader'@'%' "
                "IDENTIFIED BY 'filter_tables_password'"
            )
        )
        connection.execute(
            text("GRANT SELECT ON melty.* TO 'filter_tables_reader'@'%'")
        )

    try:
        base_config = {
            "sqlalchemy_url": limited_url,
            "filter_schemas": ["melty"],
            "is_vitess": False,
        }
        with pytest.raises(OperationalError, match="SHOW VIEW command denied"):
            _ = TapMySQL(config=base_config).catalog_dict

        filtered_config = {
            **base_config,
            "filter_tables": ["melty.filter_tables_selected"],
        }
        streams = TapMySQL(config=filtered_config).catalog_dict["streams"]

        assert [stream["stream"] for stream in streams] == [
            "melty-filter_tables_selected"
        ]
    finally:
        with root_engine.begin() as connection:
            connection.execute(
                text("DROP VIEW IF EXISTS filter_tables_restricted_view")
            )
            connection.execute(text("DROP TABLE IF EXISTS filter_tables_selected"))
            connection.execute(text("DROP USER IF EXISTS 'filter_tables_reader'@'%'"))
        root_engine.dispose()
