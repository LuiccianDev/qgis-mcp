"""Data Source Connections tools."""

from typing import Any, Literal

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import PostgreSQLConnectionParams


class ConnectionsToolset(BaseToolset):
    """MCP toolset for Browser-panel database and OGR connections."""

    domain = "connections"

    def _register_connection_discovery_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="List Connections",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List the data source connections saved in QGIS (PostgreSQL, GeoPackage, SpatiaLite, "
            "MS SQL, Oracle, ...) - the Browser panel entries. Optionally filter by provider "
            "(e.g. 'postgres', 'ogr', 'spatialite'). Passwords are redacted from the URIs.",
            structured_output=True,
        )
        async def list_connections(
            ctx: Context, provider: str | None = None, instance: str | None = None
        ) -> dict[str, Any]:
            return await _send("list_connections", {"provider": provider}, instance=instance)

        @mcp.tool(
            title="Create PostgreSQL Connection",
            description="Validate and save a new PostgreSQL Browser-panel connection. Passwords are never "
            "accepted: credentials come from a QGIS Authentication Manager configuration, from the libpq "
            "service file (pg_service.conf), or both. connection_mode selects which parameters are "
            "required; when the user's intent is unclear, ask which mode applies before calling. "
            "endpoint_using_auth_manager: host, port, database, auth_config_id (port must be the actual "
            "database port supplied by the caller or user, this tool never assumes 5432). "
            "service_using_auth_manager: service (the name defined in pg_service.conf) and auth_config_id; "
            "database optionally overrides the service file's dbname. service_only: service; database "
            "optionally overrides dbname; do not pass auth_config_id. Parameters a mode does not use are "
            "rejected. Fails if name already exists or the database cannot be reached. ssl_mode is one of "
            "prefer (default), disable, allow, require, verify-ca, or verify-full.",
            structured_output=True,
        )
        async def create_postgresql_connection(
            ctx: Context,
            name: str,
            connection_mode: Literal[
                "endpoint_using_auth_manager", "service_using_auth_manager", "service_only"
            ],
            host: str | None = None,
            port: int | None = None,
            database: str | None = None,
            auth_config_id: str | None = None,
            ssl_mode: str = "prefer",
            service: str | None = None,
            instance: str | None = None,
        ) -> dict[str, Any]:
            validated = self.validate(
                PostgreSQLConnectionParams, name=name, port=port, ssl_mode=ssl_mode
            )
            return await _send(
                "create_postgresql_connection",
                {
                    "name": validated.name,
                    "connection_mode": connection_mode,
                    "host": host,
                    "port": validated.port,
                    "database": database,
                    "auth_config_id": auth_config_id,
                    "ssl_mode": validated.ssl_mode,
                    "service": service,
                },
                timeout=timeout_long,
                instance=instance,
            )

        @mcp.tool(
            title="List Connection Tables",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List tables reachable through a saved connection. On providers with schemas "
            "(PostgreSQL), omit schema to get the schema list first, then pass one. Returns each table's "
            "geometry column, CRS, primary key and kind.",
            structured_output=True,
        )
        async def list_connection_tables(
            ctx: Context,
            provider: str,
            connection: str,
            schema: str | None = None,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send(
                "list_connection_tables",
                {"provider": provider, "connection": connection, "schema": schema},
                instance=instance,
            )

    def _register_connection_layer_and_sql_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive
        make_layer_response = self.context.make_layer_response
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Add Layer from Connection",
            description="Load a table from a saved connection as a project layer. Pass table (+ schema), "
            "or sql to build a query layer executed by the database. For a SQL layer, geometry_column "
            "and primary_key may be needed for QGIS to map/identify the result.",
        )
        async def add_layer_from_connection(
            ctx: Context,
            provider: str,
            connection: str,
            table: str | None = None,
            schema: str | None = None,
            sql: str | None = None,
            geometry_column: str | None = None,
            primary_key: str | None = None,
            name: str | None = None,
            instance: str | None = None,
        ) -> list:
            result = await _send(
                "add_layer_from_connection",
                {
                    "provider": provider,
                    "connection": connection,
                    "table": table,
                    "schema": schema,
                    "sql": sql,
                    "geometry_column": geometry_column,
                    "primary_key": primary_key,
                    "name": name,
                },
                timeout=timeout_long,
                instance=instance,
            )
            return make_layer_response(result)

        @mcp.tool(
            title="Import Layer to Connection",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Write a loaded vector layer into a saved connection as a new table "
            "(PostgreSQL, GeoPackage, ...). Fails if the table exists unless overwrite=true.",
        )
        async def import_layer_to_connection(
            ctx: Context,
            layer_id: str,
            provider: str,
            connection: str,
            table: str,
            schema: str | None = None,
            overwrite: bool = False,
            instance: str | None = None,
        ) -> dict:
            if overwrite and not await _confirm_destructive(
                ctx,
                f"Overwrite table '{table}' in connection '{connection}'? This cannot be undone.",
            ):
                return {"ok": False, "message": "Cancelled by user"}
            await ctx.info(f"Importing layer {layer_id} into {connection}.{table}")
            return await _send(
                "import_layer_to_connection",
                {
                    "layer_id": layer_id,
                    "provider": provider,
                    "connection": connection,
                    "table": table,
                    "schema": schema,
                    "overwrite": overwrite,
                },
                timeout=timeout_long,
                instance=instance,
            )

        @mcp.tool(
            title="Execute Connection SQL",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Run SQL directly on the database behind a saved connection (server-side, not a "
            "virtual layer - use execute_sql for that). Can modify the database: DDL/DML run as issued. "
            "limit caps returned rows (-1 for all).",
        )
        async def execute_connection_sql(
            ctx: Context,
            provider: str,
            connection: str,
            sql: str,
            limit: int = 100,
            instance: str | None = None,
        ) -> dict[str, Any]:
            if not await _confirm_destructive(
                ctx, f"Run SQL on connection '{connection}'?\n\n{sql}"
            ):
                return {"ok": False, "message": "Cancelled by user"}
            return await _send(
                "execute_connection_sql",
                {"provider": provider, "connection": connection, "sql": sql, "limit": limit},
                timeout=timeout_long,
                instance=instance,
            )

    def register(self) -> None:
        self._register_connection_discovery_tools()
        self._register_connection_layer_and_sql_tools()
