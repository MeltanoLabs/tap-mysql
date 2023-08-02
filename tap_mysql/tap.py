"""mysql tap class."""
from __future__ import annotations

import io
from functools import cached_property
from typing import Any, Mapping, cast

from singer_sdk import SQLTap, Stream
from singer_sdk import typing as th  # JSON schema typing helpers
from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url

from tap_mysql.client import MySQLConnector, MySQLStream


class TapMySQL(SQLTap):
    """Singer tap for MySQL."""

    name = "tap-mysql"
    default_stream_class = MySQLStream

    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        """Constructor.

        Should use JSON Schema instead
        See https://github.com/MeltanoLabs/tap-postgres/issues/141
        """
        super().__init__(*args, **kwargs)
        assert (self.config.get("sqlalchemy_url") is not None) or (
            self.config.get("host") is not None
            and self.config.get("port") is not None
            and self.config.get("user") is not None
            and self.config.get("password") is not None
        ), (
            "Need either the sqlalchemy_url to be set or host, port, user,"
            + " and password to be set"
        )

    config_jsonschema = th.PropertiesList(
        th.Property(
            "host",
            th.StringType,
            description=(
                "Hostname for mysql instance. "
                + "Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "port",
            th.IntegerType,
            default=3306,
            description=(
                "The port on which mysql is awaiting connection. "
                + "Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "user",
            th.StringType,
            description=(
                "User name used to authenticate. "
                + "Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "password",
            th.StringType,
            secret=True,
            description=(
                "Password used to authenticate. "
                "Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "database",
            th.StringType,
            description=(
                "Database name. "
                + "Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "sqlalchemy_url",
            th.StringType,
            secret=True,
            description=(
                "Example mysql://[username]:[password]@localhost:3306/[db_name]"
            ),
        ),
    ).to_dict()

    def get_sqlalchemy_url(self, config: Mapping[str, Any]) -> str:
        """Generate a SQLAlchemy URL.

        Args:
            config: The configuration for the connector.
        """
        if config.get("sqlalchemy_url"):
            return cast(str, config["sqlalchemy_url"])

        else:
            sqlalchemy_url = URL.create(
                drivername="mysql+pymysql",
                username=config["user"],
                password=config["password"],
                host=config["host"],
                port=config["port"],
                database=config["database"],
            )
            return cast(str, sqlalchemy_url)

    @cached_property
    def connector(self) -> MySQLConnector:
        """Get a configured connector for this Tap.

        Connector is a singleton (one instance is used by the Tap and Streams).

        """
        url = make_url(self.get_sqlalchemy_url(config=self.config))

        return MySQLConnector(
            config=dict(self.config),
            sqlalchemy_url=url.render_as_string(hide_password=False),
        )

    @property
    def catalog_dict(self) -> dict:
        """Get catalog dictionary.

        Returns:
            The tap's catalog as a dict
        """
        if self._catalog_dict:
            return self._catalog_dict

        if self.input_catalog:
            return self.input_catalog.to_dict()

        result: dict[str, list[dict]] = {"streams": []}
        result["streams"].extend(self.connector.discover_catalog_entries())

        self._catalog_dict: dict = result
        return self._catalog_dict

    def discover_streams(self) -> list[Stream]:
        """Initialize all available streams and return them as a list.

        Returns:
            List of discovered Stream objects.
        """
        return [
            MySQLStream(self, catalog_entry, connector=self.connector)
            for catalog_entry in self.catalog_dict["streams"]
        ]
