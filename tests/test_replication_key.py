"""Tests standard tap features using the built-in SDK tests library."""
# flake8: noqa

import json

import datetime
from singer_sdk.testing.templates import TapTestTemplate
from singer_sdk._singerlib import Catalog

from tap_mysql.tap import TapMySQL

TABLE_NAME = "test_replication_key"
SAMPLE_CONFIG = {
    "start_date": datetime.datetime(2022, 11, 1).isoformat(),
    # Using 127.0.0.1 instead of localhost because of mysqlclient dialect.
    # See: https://stackoverflow.com/questions/72294279/how-to-connect-to-mysql-databas-using-github-actions
    "sqlalchemy_url": "mysql+pymysql://root:password@127.0.0.1:3306/melty",
}


def replication_key_test(tap, table_name):
    """Originally built to address
    https://github.com/meltano/sdk/issues/1268.
    """
    tap.run_discovery()
    catalog = Catalog.from_dict({"streams": tap.catalog_dict["streams"]})

    for stream in catalog.streams:
        if table_name not in stream.tap_stream_id:
            stream.metadata.root.selected = False
        else:
            stream.metadata.root.selected = True
            stream.metadata.root.forced_replication_method = "INCREMENTAL"
            stream.replication_key = "updated_at"
            stream.metadata.root.replication_key = "updated_at"

    tap = TapMySQL(config=SAMPLE_CONFIG, catalog=catalog.to_dict())
    tap.sync_all()


class TapTestReplicationKey(TapTestTemplate):
    """Test class for tap replication key tests."""

    name = "replication_key"
    table_name = TABLE_NAME

    def test(self):
        """Run the replication key test."""
        replication_key_test(self.tap, self.table_name)
