"""Tests selected columns only from stream."""
# flake8: noqa
import json

from singer_sdk.testing.templates import TapTestTemplate

from tap_mysql.tap import TapMySQL

TABLE_NAME_SELECTED_COLUMNS_ONLY = "test_selected_columns_only"
SAMPLE_CONFIG = {
    # Using 127.0.0.1 instead of localhost because of mysqlclient dialect.
    # See: https://stackoverflow.com/questions/72294279/how-to-connect-to-mysql-databas-using-github-actions
    "sqlalchemy_url": f"mysql+mysqldb://root:password@127.0.0.1:3306/melty",
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

    def test(self):
        selected_columns_only_test(self.tap, self.table_name)
