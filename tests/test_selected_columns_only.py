"""Tests selected columns only from stream."""

# flake8: noqa
import json

import pytest
from singer_sdk.testing import get_tap_test_class, suites
from singer_sdk.testing.templates import TapTestTemplate

from tap_mysql.tap import TapMySQL

from .test_core import setup_test_table, teardown_test_table

TABLE_NAME_SELECTED_COLUMNS_ONLY = "test_selected_columns_only"
SAMPLE_CONFIG = {
    # Using 127.0.0.1 instead of localhost because of mysqlclient dialect.
    # See: https://stackoverflow.com/questions/72294279/how-to-connect-to-mysql-databas-using-github-actions
    "sqlalchemy_url": f"mysql+pymysql://root:password@127.0.0.1:3306/melty",
}


def selected_columns_only_test(tap, table_name):
    """Excluding one column from stream and check if it is not present in query."""
    column_to_exclude = "name"
    tap.run_discovery()
    tap_catalog = json.loads(tap.catalog_json_text)
    for stream in tap_catalog["streams"]:
        if stream.get("stream") and table_name not in stream["stream"]:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = False
        else:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = True
                if metadata["breadcrumb"] != []:
                    if metadata["breadcrumb"][1] == column_to_exclude:
                        metadata["metadata"]["selected"] = False

    tap = TapMySQL(config=SAMPLE_CONFIG, catalog=tap_catalog)
    streams = tap.discover_streams()
    selected_stream = next(s for s in streams if s.selected is True)

    for row in selected_stream.get_records(context=None):
        assert column_to_exclude not in row


class TapTestSelectedColumnsOnly(TapTestTemplate):
    name = "selected_columns_only"
    table_name = TABLE_NAME_SELECTED_COLUMNS_ONLY


custom_test_selected_columns_only = suites.TestSuite(
    kind="tap",
    tests=[TapTestSelectedColumnsOnly],
)

with open("tests/resources/data_selected_columns_only.json", "r") as f:
    catalog_dict = json.load(f)

# creating testing instance for isolated table in mysql
TapMySQLTestSelectedColumnsOnly = get_tap_test_class(
    tap_class=TapMySQL,
    config=SAMPLE_CONFIG,
    catalog=catalog_dict,
    custom_suites=[custom_test_selected_columns_only],
)


class TestTapMySQLSelectedColumnsOnly(TapMySQLTestSelectedColumnsOnly):
    table_name = TABLE_NAME_SELECTED_COLUMNS_ONLY
    sqlalchemy_url = SAMPLE_CONFIG["sqlalchemy_url"]

    @pytest.fixture(scope="class")
    def resource(self):
        setup_test_table(self.table_name, self.sqlalchemy_url)
        yield
        teardown_test_table(self.table_name, self.sqlalchemy_url)
