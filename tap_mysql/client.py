"""SQL client handling."""
from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Iterable

import singer_sdk.helpers._typing
import sqlalchemy
from singer_sdk import SQLConnector, SQLStream
from singer_sdk import typing as th
from singer_sdk._singerlib import CatalogEntry, MetadataMapping, Schema
from singer_sdk.helpers._typing import TypeConformanceLevel

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.engine.reflection import Inspector

unpatched_conform = (
    singer_sdk.helpers._typing._conform_primitive_property  # noqa: SLF001
)


def patched_conform(
    elem: Any,  # noqa: ANN401
    property_schema: dict,
) -> Any:  # noqa: ANN401
    """Override type conformance to prevent dates turning into datetimes.

    Converts a primitive to a json compatible type.

    Returns:
        The appropriate json compatible type.
    """
    if isinstance(elem, datetime.date):
        return elem.isoformat()
    return unpatched_conform(elem=elem, property_schema=property_schema)


singer_sdk.helpers._typing._conform_primitive_property = patched_conform  # noqa: SLF001


class MySQLConnector(SQLConnector):
    """Connects to the MySQL SQL source."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the SQL connector.

        This method initializes the SQL connector with the provided arguments.
        It can accept variable-length arguments and keyword arguments to
        customize the connection settings.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        # Check if we are using PlanetScale,
        # if so we need to let our connector know
        # Ideally we'd just check to see if we're on Vitess,
        # but I don't know how to do that quickly
        self.is_vitess = False

        if self.config.get("is_vitess") is None:
            self.logger.info(
                "No is_vitess configuration provided, dynamically checking if "
                "we are using a Vitess instance."
            )
            with self._connect() as conn:
                output = conn.execute(
                    "select variable_value from "
                    "performance_schema.global_variables where "
                    "variable_name='version_comment' and variable_value like "
                    "'PlanetScale%%'"
                )
                rows = output.fetchall()
                if len(rows) > 0:
                    self.logger.info(
                        "Instance has been detected to be a "
                        "Vitess (PlanetScale) instance, using Vitess "
                        "configuration."
                    )
                    self.is_vitess = True
            self.logger.info(
                "Instance is not a Vitess instance, using standard configuration."
            )

    @staticmethod
    def to_jsonschema_type(
        sql_type: str  # noqa: ANN401
        | sqlalchemy.types.TypeEngine
        | type[sqlalchemy.types.TypeEngine]
        | Any,
    ) -> dict:
        """Return a JSON Schema representation of the provided type.

        Overridden from SQLConnector to correctly handle JSONB and Arrays.

        By default will call `typing.to_jsonschema_type()` for strings and
        SQLAlchemy types.

        Args:
            sql_type: The string representation of the SQL type, a SQLAlchemy
                TypeEngine class or object, or a custom-specified object.

        Raises:
            ValueError: If the type received could not be translated to
            jsonschema.

        Returns:
            The JSON Schema representation of the provided type.

        """
        type_name = None
        if isinstance(sql_type, str):
            type_name = sql_type
        elif isinstance(sql_type, sqlalchemy.types.TypeEngine):
            type_name = type(sql_type).__name__

        if type_name is not None and type_name in ("JSONB", "JSON"):
            return th.ObjectType().type_dict

        # if (
        #     type_name is not None
        #     and isinstance(sql_type, sqlalchemy.dialects.mysql)
        #     and type_name == "ARRAY"
        # ):
        return MySQLConnector.sdk_typing_object(sql_type).type_dict

    @staticmethod
    def sdk_typing_object(
        from_type: str
        | sqlalchemy.types.TypeEngine
        | type[sqlalchemy.types.TypeEngine],
    ) -> (
        th.DateTimeType
        | th.NumberType
        | th.IntegerType
        | th.DateType
        | th.StringType
        | th.BooleanType
    ):
        """Return the JSON Schema dict that describes the sql type.

        Args:
            from_type: The SQL type as a string or as a TypeEngine. If a TypeEngine is
                provided, it may be provided as a class or a specific object instance.

        Raises:
            ValueError: If the `from_type` value is not of type `str` or `TypeEngine`.

        Returns:
            A compatible JSON Schema type definition.

        """
        sqltype_lookup: dict[
            str,
            th.DateTimeType
            | th.NumberType
            | th.IntegerType
            | th.DateType
            | th.StringType
            | th.BooleanType,
        ] = {
            # NOTE: This is an ordered mapping, with earlier mappings taking
            # precedence. If the SQL-provided type contains the type name on
            #  the left, the mapping will return the respective singer type.
            "timestamp": th.DateTimeType(),
            "datetime": th.DateTimeType(),
            "date": th.DateType(),
            "int": th.IntegerType(),
            "numeric": th.NumberType(),
            "decimal": th.NumberType(),
            "double": th.NumberType(),
            "float": th.NumberType(),
            "string": th.StringType(),
            "text": th.StringType(),
            "char": th.StringType(),
            "bool": th.BooleanType(),
            "variant": th.StringType(),
        }
        if isinstance(from_type, str):
            type_name = from_type
        elif isinstance(from_type, sqlalchemy.types.TypeEngine):
            type_name = type(from_type).__name__
        elif isinstance(from_type, type) and issubclass(
            from_type,
            sqlalchemy.types.TypeEngine,
        ):
            type_name = from_type.__name__
        else:
            msg = "Expected `str` or a SQLAlchemy `TypeEngine` object or type."
            raise TypeError(
                msg,
            )

        # Look for the type name within the known SQL type names:
        for sqltype, jsonschema_type in sqltype_lookup.items():
            if sqltype.lower() in type_name.lower():
                return jsonschema_type

        return sqltype_lookup["string"]  # safe failover to str

    def get_schema_names(self, engine: Engine, inspected: Inspector) -> list[str]:
        """Return a list of schema names in DB, or overrides with user-provided values.

        Args:
            engine: SQLAlchemy engine
            inspected: SQLAlchemy inspector instance for engine

        Returns:
            List of schema names
        """
        if "filter_schemas" in self.config and len(self.config["filter_schemas"]) != 0:
            return self.config["filter_schemas"]
        return super().get_schema_names(engine, inspected)

    def discover_catalog_entry(  # noqa: PLR0913
        self,
        engine: Engine,
        inspected: Inspector,
        schema_name: str,
        table_name: str,
        is_view: bool,  # noqa: FBT001
    ) -> CatalogEntry:
        """Overrode to support Vitess as DESCRIBE is not supported for views.

        Create `CatalogEntry` object for the given table or a view.

        Args:
            engine: SQLAlchemy engine
            inspected: SQLAlchemy inspector instance for engine
            schema_name: Schema name to inspect
            table_name: Name of the table or a view
            is_view: Flag whether this object is a view, returned by `get_object_names`

        Returns:
            `CatalogEntry` object for the given table or a view
        """
        if self.is_vitess is False or is_view is False:
            return super().discover_catalog_entry(
                engine, inspected, schema_name, table_name, is_view
            )
        # For vitess views, we can't use DESCRIBE as it's not supported for
        # views so we do the below.
        unique_stream_id = self.get_fully_qualified_name(
            db_name=None,
            schema_name=schema_name,
            table_name=table_name,
            delimiter="-",
        )

        # Initialize columns list
        table_schema = th.PropertiesList()
        with self._connect() as conn:
            columns = conn.execute(f"SHOW columns from `{schema_name}`.`{table_name}`")
            for column in columns:
                column_name = column["Field"]
                is_nullable = column["Null"] == "YES"
                jsonschema_type: dict = self.to_jsonschema_type(column["Type"])
                table_schema.append(
                    th.Property(
                        name=column_name,
                        wrapped=th.CustomType(jsonschema_type),
                        required=not is_nullable,
                    ),
                )
        schema = table_schema.to_dict()

        # Initialize available replication methods
        addl_replication_methods: list[str] = [""]  # By default an empty list.
        # Notes regarding replication methods:
        # - 'INCREMENTAL' replication must be enabled by the user by specifying
        #   a replication_key value.
        # - 'LOG_BASED' replication must be enabled by the developer, according
        #   to source-specific implementation capabilities.
        replication_method = next(reversed(["FULL_TABLE", *addl_replication_methods]))

        # Create the catalog entry object
        return CatalogEntry(
            tap_stream_id=unique_stream_id,
            stream=unique_stream_id,
            table=table_name,
            key_properties=None,
            schema=Schema.from_dict(schema),
            is_view=is_view,
            replication_method=replication_method,
            metadata=MetadataMapping.get_standard_metadata(
                schema_name=schema_name,
                schema=schema,
                replication_method=replication_method,
                key_properties=None,
                valid_replication_keys=None,  # Must be defined by user
            ),
            database=None,  # Expects single-database context
            row_count=None,
            stream_alias=None,
            replication_key=None,  # Must be defined by user
        )

    def get_sqlalchemy_type(self, col_meta_type: str) -> sqlalchemy.Column:
        """Return a SQLAlchemy type object for the given SQL type.

        Used ischema_names so we don't have to manually map all types.
        """
        dialect = sqlalchemy.dialects.mysql.base.dialect()  # type: ignore[attr-defined]
        ischema_names = dialect.ischema_names
        # Example varchar(97)
        type_info = col_meta_type.split("(")
        base_type_name = type_info[0].split(" ")[0]  # bigint unsigned
        type_args = (
            type_info[1].split(" ")[0].rstrip(")") if len(type_info) > 1 else None
        )  # decimal(25,4) unsigned should work

        if base_type_name in {"enum", "set"}:
            self.logger.warning(
                "Enum and Set types not supported for col_meta_type=%s. "
                "Using varchar instead.",
                col_meta_type,
            )
            base_type_name = "varchar"
            type_args = None

        type_class = ischema_names.get(base_type_name.lower())

        try:
            # Create an instance of the type class with parameters if they exist
            if type_args:
                return type_class(
                    *map(int, type_args.split(","))
                )  # Want to create a varchar(97) if asked for
            return type_class()
        except Exception:
            self.logger.exception(
                "Error creating sqlalchemy type for col_meta_type=%s", col_meta_type
            )
            raise

    def get_table_columns(
        self,
        full_table_name: str,
        column_names: list[str] | None = None,
    ) -> dict[str, sqlalchemy.Column]:
        """Overrode to support Vitess as DESCRIBE is not supported for views.

        Return a list of table columns.

        Args:
            full_table_name: Fully qualified table name.
            column_names: A list of column names to filter to.

        Returns:
            An ordered list of column objects.
        """
        if self.is_vitess is False:
            return super().get_table_columns(full_table_name, column_names)
        # If Vitess Instance then we can't use DESCRIBE as it's not supported
        # for views so we do below
        if full_table_name not in self._table_cols_cache:
            _, schema_name, table_name = self.parse_full_table_name(full_table_name)
            with self._connect() as conn:
                columns = conn.execute(
                    f"SHOW columns from `{schema_name}`.`{table_name}`"
                )
                self._table_cols_cache[full_table_name] = {
                    col_meta["Field"]: sqlalchemy.Column(
                        col_meta["Field"],
                        self.get_sqlalchemy_type(col_meta["Type"]),
                        nullable=col_meta["Null"] == "YES",
                    )
                    for col_meta in columns
                    if not column_names
                    or col_meta["Field"].casefold()
                    in {col.casefold() for col in column_names}
                }

        return self._table_cols_cache[full_table_name]


class MySQLStream(SQLStream):
    """Stream class for MySQL streams."""

    connector_class = MySQLConnector

    # JSONB Objects won't be selected without type_confomance_level to ROOT_ONLY
    TYPE_CONFORMANCE_LEVEL = TypeConformanceLevel.ROOT_ONLY

    def get_records(self, context: dict | None) -> Iterable[dict[str, Any]]:
        """Return a generator of row-type dictionary objects.

        If the stream has a replication_key value defined, records will be sorted by the
        incremental key. If the stream also has an available starting bookmark, the
        records will be filtered for values greater than or equal to the bookmark value.

        Args:
            context: If partition context is provided, will read specifically from this
                data slice.

        Yields:
            One dict per record.

        Raises:
            NotImplementedError: If partition is passed in context and the stream does
                not support partitioning.

        """
        if context:
            msg = f"Stream '{self.name}' does not support partitioning."
            raise NotImplementedError(
                msg,
            )

        # pulling rows with only selected columns from stream
        selected_column_names = list(self.get_selected_schema()["properties"])
        table = self.connector.get_table(
            self.fully_qualified_name,
            column_names=selected_column_names,
        )
        query = table.select()
        if self.replication_key:
            replication_key_col = table.columns[self.replication_key]
            query = query.order_by(replication_key_col)

            start_val = self.get_starting_replication_key_value(context)
            if start_val:
                query = query.filter(replication_key_col >= start_val)

        with self.connector._connect() as conn:  # noqa: SLF001
            if self.connector.is_vitess:  # type: ignore[attr-defined]
                conn.exec_driver_sql(
                    "set workload=olap"
                )  # See https://github.com/planetscale/discussion/discussions/190
            for row in conn.execute(query):
                yield dict(row)
