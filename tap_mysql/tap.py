"""mysql tap class."""

from __future__ import annotations

import atexit
import io
import signal
import sys
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

import paramiko
from singer_sdk import SQLTap, Stream
from singer_sdk import typing as th  # JSON schema typing helpers
from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url
from sshtunnel import SSHTunnelForwarder

from tap_mysql.client import MySQLConnector, MySQLStream

if TYPE_CHECKING:
    from collections.abc import Mapping


class TapMySQL(SQLTap):
    """Singer tap for MySQL."""

    name = "tap-mysql"
    default_stream_class = MySQLStream

    def __init__(
        self,
        *args: tuple,
        **kwargs: dict,
    ) -> None:
        """Construct a MySQL tap.

        Should use JSON Schema instead
        See https://github.com/meltano/sdk/pull/1525
        """
        super().__init__(*args, **kwargs)
        sql_alchemy_url_exists = self.config.get("sqlalchemy_url") is not None
        individual_url_params_exist = all(
            [
                self.config.get("host") is not None,
                self.config.get("port") is not None,
                self.config.get("user") is not None,
                self.config.get("password") is not None,
            ]
        )
        if not (sql_alchemy_url_exists or individual_url_params_exist):
            msg = (
                "Need either the sqlalchemy_url to be set or host, port, "
                "user, and password to be set"
            )
            raise ValueError(msg)

    config_jsonschema = th.PropertiesList(
        th.Property(
            "host",
            th.StringType,
            description=(
                "Hostname for mysql instance. "
                "Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "port",
            th.IntegerType,
            default=3306,
            description=(
                "The port on which mysql is awaiting connection. "
                "Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "user",
            th.StringType,
            description=(
                "User name used to authenticate. "
                "Note if sqlalchemy_url is set this will be ignored."
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
                "Database name. Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "sqlalchemy_options",
            th.ObjectType(additional_properties=th.StringType),
            description=(
                "sqlalchemy_url options (also called the query), to connect to "
                "PlanetScale you must turn on SSL see PlanetScale information "
                "below. Note if sqlalchemy_url is set this will be ignored."
            ),
        ),
        th.Property(
            "sqlalchemy_url",
            th.StringType,
            secret=True,
            description=(
                "Example pymysql://[username]:[password]@localhost:3306/[db_name][?options] "  # noqa: E501
                "see https://docs.sqlalchemy.org/en/20/dialects/mysql.html#module-sqlalchemy.dialects.mysql.pymysql "  # noqa: E501
                "for more information"
            ),
        ),
        th.Property(
            "filter_schemas",
            th.ArrayType(th.StringType),
            description=(
                "If an array of schema names is provided, the tap will only process "
                "the specified MySQL schemas and ignore others. If left blank, the "
                "tap automatically determines ALL available MySQL schemas."
            ),
        ),
        th.Property(
            "is_vitess",
            th.BooleanType,
            default=None,
            description=(
                "By default we'll check if the database is a Vitess instance. "
                "If you would rather not automatically check, set this to "
                "`False`. See Vitess/PlanetScale documentation below for more "
                "information."
            ),
        ),
        th.Property(
            "ssh_tunnel",
            th.ObjectType(
                th.Property(
                    "enable",
                    th.BooleanType,
                    required=True,
                    default=False,
                    description=(
                        "Enable an ssh tunnel (also known as bastion host), see the "
                        "other ssh_tunnel.* properties for more details"
                    ),
                ),
                th.Property(
                    "host",
                    th.StringType,
                    required=True,
                    default="localhost",
                    description=(
                        "Host of the bastion host, this is the host "
                        "we'll connect to via ssh"
                    ),
                ),
                th.Property(
                    "username",
                    th.StringType,
                    required=True,
                    default="root",
                    description="Username to connect to bastion host",
                ),
                th.Property(
                    "port",
                    th.IntegerType,
                    required=True,
                    default=22,
                    description="Port to connect to bastion host",
                ),
                th.Property(
                    "private_key",
                    th.StringType,
                    required=False,
                    secret=True,
                    description="Private Key for authentication to the bastion host",
                ),
                th.Property(
                    "private_key_password",
                    th.StringType,
                    required=False,
                    secret=True,
                    default=None,
                    description=(
                        "Private Key Password, leave None if no password is set"
                    ),
                ),
            ),
            required=False,
            description="SSH Tunnel Configuration, this is a json object",
        ),
    ).to_dict()

    def get_sqlalchemy_url(self, config: Mapping[str, Any]) -> str:
        """Generate a SQLAlchemy URL.

        Args:
            config: The configuration for the connector.
        """
        if config.get("sqlalchemy_url"):
            return cast(str, config["sqlalchemy_url"])

        sqlalchemy_url = URL.create(
            drivername="mysql+pymysql",
            username=config["user"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
            database=config["database"],
            query=config.get("sqlalchemy_options"),  # type: ignore[arg-type]
        )
        return cast(str, sqlalchemy_url)

    @cached_property
    def connector(self) -> MySQLConnector:
        """Get a configured connector for this Tap.

        Connector is a singleton (one instance is used by the Tap and Streams).

        """
        url = make_url(self.get_sqlalchemy_url(config=self.config))
        ssh_config = self.config.get("ssh_tunnel", {})

        if ssh_config.get("enable", False):
            # Return a new URL with SSH tunnel parameters
            url = self.ssh_tunnel_connect(ssh_config=ssh_config, url=url)

        return MySQLConnector(
            config=dict(self.config),
            sqlalchemy_url=url.render_as_string(hide_password=False),
        )

    def guess_key_type(self, key_data: str) -> paramiko.PKey:
        """Guess the type of the private key.

        We are duplicating some logic from the ssh_tunnel package here,
        we could try to use their function instead.

        Args:
            key_data: The private key data to guess the type of.

        Returns:
            The private key object.

        Raises:
            ValueError: If the key type could not be determined.
        """
        for key_class in (
            paramiko.RSAKey,
            paramiko.DSSKey,
            paramiko.ECDSAKey,
            paramiko.Ed25519Key,
        ):
            try:
                key = key_class.from_private_key(io.StringIO(key_data))  # type: ignore[attr-defined]
            except paramiko.SSHException:  # noqa: PERF203
                continue
            else:
                return key

        errmsg = "Could not determine the key type."
        raise ValueError(errmsg)

    def ssh_tunnel_connect(self, *, ssh_config: dict[str, Any], url: URL) -> URL:
        """Connect to the SSH Tunnel and swap the URL to use the tunnel.

        Args:
            ssh_config: The SSH Tunnel configuration
            url: The original URL to connect to.

        Returns:
            The new URL to connect to, using the tunnel.
        """
        if key_data := ssh_config.get("private_key"):
            private_key = self.guess_key_type(key_data)
        else:
            private_key = None

        self.ssh_tunnel: SSHTunnelForwarder = SSHTunnelForwarder(
            ssh_address_or_host=(ssh_config["host"], ssh_config["port"]),
            ssh_username=ssh_config["username"],
            ssh_pkey=self.guess_key_type(ssh_config["private_key"]),
            ssh_private_key_password=ssh_config.get("private_key_password"),
            remote_bind_address=(url.host, url.port),
        )
        self.ssh_tunnel.start()
        self.logger.info("SSH Tunnel started")
        # On program exit clean up, want to also catch signals
        atexit.register(self.clean_up)
        signal.signal(signal.SIGTERM, self.catch_signal)
        # Probably overkill to catch SIGINT, but needed for SIGTERM
        signal.signal(signal.SIGINT, self.catch_signal)

        # Swap the URL to use the tunnel
        return url.set(
            host=self.ssh_tunnel.local_bind_host,
            port=self.ssh_tunnel.local_bind_port,
        )

    def clean_up(self) -> None:
        """Stop the SSH Tunnel."""
        if self.logger and self.logger.handlers:
            self.logger.info("Shutting down SSH Tunnel")
        self.ssh_tunnel.stop()

    def catch_signal(self, signum, frame) -> None:  # noqa: ANN001 ARG002
        """Catch signals and exit cleanly.

        Args:
            signum: The signal number
            frame: The current stack frame
        """
        sys.exit(1)  # Calling this to be sure atexit is called, so clean_up gets called

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
