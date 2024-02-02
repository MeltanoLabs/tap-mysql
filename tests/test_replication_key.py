"""Tests standard tap features using the built-in SDK tests library."""
# flake8: noqa

import json

import pendulum
from singer_sdk.testing.templates import TapTestTemplate

from tap_mysql.tap import TapMySQL

TABLE_NAME = "test_replication_key"
SAMPLE_CONFIG = {
    "start_date": pendulum.datetime(2022, 11, 1).to_iso8601_string(),
    # Using 127.0.0.1 instead of localhost because of mysqlclient dialect.
    # See: https://stackoverflow.com/questions/72294279/how-to-connect-to-mysql-databas-using-github-actions
    "sqlalchemy_url": f"mysql+pymysql://root:password@127.0.0.1:3306/melty",
}


def replication_key_test(tap, table_name):
    """Originally built to address
    https://github.com/MeltanoLabs/tap-postgres/issues/9.
    """
    tap.run_discovery()
    # TODO Switch this to using Catalog from _singerlib as it makes iterating
    # over this stuff easier
    tap_catalog = json.loads(tap.catalog_json_text)
    for stream in tap_catalog["streams"]:
        if stream.get("stream") and table_name not in stream["stream"]:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = False
        else:
            # Without this the tap will not do an INCREMENTAL sync properly
            stream["replication_key"] = "updated_at"
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = True
                if metadata["breadcrumb"] == []:
                    metadata["metadata"]["replication-method"] = "INCREMENTAL"
                    metadata["metadata"]["replication-key"] = "updated_at"

    # Handy for debugging
    # with open('data.json', 'w', encoding='utf-8') as f:

    tap = TapMySQL(config=SAMPLE_CONFIG, catalog=tap_catalog)
    tap.sync_all()


class TapTestReplicationKey(TapTestTemplate):
    name = "replication_key"
    table_name = TABLE_NAME

    def test(self):
        replication_key_test(self.tap, self.table_name)
