# flake8: noqa

import copy
import datetime
import decimal
import json

import pytest
import sqlalchemy
from faker import Faker
from singer_sdk.testing import get_tap_test_class, suites
from singer_sdk.testing.runners import TapTestRunner
from sqlalchemy import Column, DateTime, Integer, MetaData, Numeric, String, Table, text
from sqlalchemy.dialects.mysql import DATE, DATETIME, JSON, TIME

from tap_mysql.tap import TapMySQL

from .test_replication_key import TABLE_NAME, TapTestReplicationKey

SAMPLE_CONFIG = {
    "start_date": datetime.datetime(2022, 11, 1).isoformat(),
    # Using 127.0.0.1 instead of localhost because of mysqlclient dialect.
    # See: https://stackoverflow.com/questions/72294279/how-to-connect-to-mysql-databas-using-github-actions
    "sqlalchemy_url": "mysql+pymysql://root:password@127.0.0.1:3306/melty",
}

NO_SQLALCHEMY_CONFIG = {
    "start_date": datetime.datetime(2022, 11, 1).isoformat(),
    # Using 127.0.0.1 instead of localhost because of mysqlclient dialect.
    # See: https://stackoverflow.com/questions/72294279/how-to-connect-to-mysql-databas-using-github-actions
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "password",
    "database": "melty",
}


def setup_test_table(table_name, sqlalchemy_url):
    """Setup any state specific to the execution of the given module."""
    engine = sqlalchemy.create_engine(sqlalchemy_url)
    fake = Faker()

    date1 = datetime.date(2022, 11, 1)
    date2 = datetime.date(2022, 11, 30)
    metadata_obj = MetaData()
    test_replication_key_table = Table(
        table_name,
        metadata_obj,
        Column("id", Integer, primary_key=True),
        Column("updated_at", DateTime(), nullable=False),
        Column("name", String(length=100)),
    )
    with engine.connect() as conn:
        with conn.begin():  # Ensure transaction is committed
            metadata_obj.create_all(conn)
            conn.execute(text(f"TRUNCATE TABLE {table_name}"))
            for _ in range(5):
                insert = test_replication_key_table.insert().values(
                    updated_at=fake.date_time_between(date1, date2),
                    name=fake.name(),
                )
                conn.execute(insert)


def teardown_test_table(table_name, sqlalchemy_url):
    engine = sqlalchemy.create_engine(sqlalchemy_url)
    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE {table_name}"))


custom_test_replication_key = suites.TestSuite(
    kind="tap",
    tests=[TapTestReplicationKey],
)

with open("tests/resources/data.json") as f:
    catalog_dict = json.load(f)

TapMySQLTest = get_tap_test_class(
    tap_class=TapMySQL,
    config=SAMPLE_CONFIG,
    catalog=catalog_dict,
    custom_suites=[custom_test_replication_key],
)

TapMySQLTestNOSQLALCHEMY = get_tap_test_class(
    tap_class=TapMySQL,
    config=NO_SQLALCHEMY_CONFIG,
    catalog=catalog_dict,
    custom_suites=[custom_test_replication_key],
)


class TestTapMySQL(TapMySQLTest):
    table_name = TABLE_NAME
    sqlalchemy_url = SAMPLE_CONFIG["sqlalchemy_url"]

    @pytest.fixture(scope="class")
    def resource(self):
        setup_test_table(self.table_name, self.sqlalchemy_url)
        yield
        teardown_test_table(self.table_name, self.sqlalchemy_url)


class TestTapMySQL_NOSQLALCHMY(TapMySQLTestNOSQLALCHEMY):
    table_name = TABLE_NAME
    sqlalchemy_url = SAMPLE_CONFIG["sqlalchemy_url"]

    @pytest.fixture(scope="class")
    def resource(self):
        setup_test_table(self.table_name, self.sqlalchemy_url)
        yield
        teardown_test_table(self.table_name, self.sqlalchemy_url)


def test_temporal_datatypes():
    """Dates were being incorrectly parsed as date times (issue #171).

    This test checks that dates are being parsed correctly, and additionally implements
    schema checks, and performs similar tests on times and timestamps.
    """
    table_name = "test_date"
    engine = sqlalchemy.create_engine(SAMPLE_CONFIG["sqlalchemy_url"])

    metadata_obj = MetaData()
    table = Table(
        table_name,
        metadata_obj,
        Column("column_date", DATE),
        Column("column_time", TIME(timezone=False, fsp=6)),
        Column("column_timestamp", DATETIME),
    )
    with engine.connect() as conn:
        # Start a transaction
        with conn.begin():
            table.drop(engine, checkfirst=True)
            metadata_obj.create_all(engine)
            insert = table.insert().values(
                column_date="2022-03-19",
                column_time="06:04:19.222",
                column_timestamp="1918-02-03 13:00:01",
            )
            conn.execute(insert)
            # Transaction will be automatically committed here

    tap = TapMySQL(config=SAMPLE_CONFIG)
    tap_catalog = json.loads(tap.catalog_json_text)
    altered_table_name = f"melty-{table_name}"
    for stream in tap_catalog["streams"]:
        if stream.get("stream") and altered_table_name not in stream["stream"]:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = False
        else:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = True
                if metadata["breadcrumb"] == []:
                    metadata["metadata"]["replication-method"] = "FULL_TABLE"

    test_runner = MySQLTestRunner(
        tap_class=TapMySQL,
        config=SAMPLE_CONFIG,
        catalog=tap_catalog,
    )
    test_runner.sync_all()
    for schema_message in test_runner.schema_messages:
        if (
            "stream" in schema_message
            and schema_message["stream"] == altered_table_name
        ):
            assert (
                "date"
                == schema_message["schema"]["properties"]["column_date"]["format"]
            )
            assert (
                "date-time"
                == schema_message["schema"]["properties"]["column_timestamp"]["format"]
            )
    assert test_runner.records[altered_table_name][0] == {
        "column_date": "2022-03-19",
        "column_time": "06:04:19.222000",
        "column_timestamp": "1918-02-03T13:00:01",
    }


def test_jsonb_json():
    """Test JSON type handling."""
    table_name = "test_jsonb_json"
    engine = sqlalchemy.create_engine(SAMPLE_CONFIG["sqlalchemy_url"])

    metadata_obj = MetaData()
    table = Table(
        table_name,
        metadata_obj,
        Column("column_json", JSON),
    )
    with engine.connect() as conn:
        # Start a transaction
        with conn.begin():
            table.drop(engine, checkfirst=True)
            metadata_obj.create_all(engine)
            insert = table.insert().values(
                column_json={"baz": "foo"},
            )
            conn.execute(insert)
            # Transaction will be automatically committed here

    tap = TapMySQL(config=SAMPLE_CONFIG)
    tap_catalog = json.loads(tap.catalog_json_text)
    altered_table_name = f"melty-{table_name}"
    for stream in tap_catalog["streams"]:
        if stream.get("stream") and altered_table_name not in stream["stream"]:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = False
        else:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = True
                if metadata["breadcrumb"] == []:
                    metadata["metadata"]["replication-method"] = "FULL_TABLE"

    test_runner = MySQLTestRunner(
        tap_class=TapMySQL,
        config=SAMPLE_CONFIG,
        catalog=tap_catalog,
    )
    test_runner.sync_all()
    for schema_message in test_runner.schema_messages:
        if (
            "stream" in schema_message
            and schema_message["stream"] == altered_table_name
        ):
            assert (
                "object"
                in schema_message["schema"]["properties"]["column_json"]["type"]
            )
    assert test_runner.records[altered_table_name][0] == {"column_json": {"baz": "foo"}}


def test_decimal():
    """Schema was wrong for Decimal objects. Check they are correctly selected."""
    table_name = "test_decimal"
    engine = sqlalchemy.create_engine(SAMPLE_CONFIG["sqlalchemy_url"])

    metadata_obj = MetaData()
    table = Table(
        table_name,
        metadata_obj,
        Column("column", Numeric()),
    )
    with engine.connect() as conn:
        table.drop(engine, checkfirst=True)
        metadata_obj.create_all(engine)
        insert = table.insert().values(column=decimal.Decimal("3.14"))
        conn.execute(insert)
        insert = table.insert().values(column=decimal.Decimal("12"))
        conn.execute(insert)
        insert = table.insert().values(column=decimal.Decimal("10000.00001"))
        conn.execute(insert)
    tap = TapMySQL(config=SAMPLE_CONFIG)
    tap_catalog = json.loads(tap.catalog_json_text)
    altered_table_name = f"public_{table_name}"
    for stream in tap_catalog["streams"]:
        if stream.get("stream") and altered_table_name not in stream["stream"]:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = False
        else:
            for metadata in stream["metadata"]:
                metadata["metadata"]["selected"] = True
                if metadata["breadcrumb"] == []:
                    metadata["metadata"]["replication-method"] = "FULL_TABLE"

    test_runner = MySQLTestRunner(
        tap_class=TapMySQL,
        config=SAMPLE_CONFIG,
        catalog=tap_catalog,
    )
    test_runner.sync_all()
    for schema_message in test_runner.schema_messages:
        if (
            "stream" in schema_message
            and schema_message["stream"] == altered_table_name
        ):
            assert "number" in schema_message["schema"]["properties"]["column"]["type"]


def test_filter_schemas():
    """Only return tables from a given schema"""
    table_name = "test_filter_schemas"
    engine = sqlalchemy.create_engine(SAMPLE_CONFIG["sqlalchemy_url"])

    metadata_obj = MetaData()
    table = Table(table_name, metadata_obj, Column("id", Integer), schema="new_schema")

    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS new_schema"))
        table.drop(engine, checkfirst=True)
        metadata_obj.create_all(engine)
    filter_schemas_config = copy.deepcopy(SAMPLE_CONFIG)
    filter_schemas_config.update({"filter_schemas": ["new_schema"]})
    tap = TapMySQL(config=filter_schemas_config)
    tap_catalog = json.loads(tap.catalog_json_text)
    altered_table_name = f"new_schema-{table_name}"
    # Check that the only stream in the catalog is the one table put into new_schema
    assert len(tap_catalog["streams"]) == 1
    assert tap_catalog["streams"][0]["stream"] == altered_table_name


class MySQLTestRunner(TapTestRunner):
    def run_sync_dry_run(self) -> bool:
        """Dislike this function and how TestRunner does this so just hacking it here.
        Want to be able to run exactly the catalog given.
        """
        new_tap = self.new_tap()
        new_tap.sync_all()
        return True
