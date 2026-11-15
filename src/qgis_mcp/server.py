#!/usr/bin/env python3
"""
QGIS MCP Server - Exposes QGIS operations as MCP tools, resources, and prompts.
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import secrets
import socket
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from typing import Any

try:
    from mcp.server.fastmcp.prompts.base import UserMessage
except ModuleNotFoundError:  # mcp >= 2.0 renamed fastmcp -> mcpserver
    from mcp.server.mcpserver.prompts.base import UserMessage
try:
    from mcp.shared.exceptions import McpError
except ImportError:  # mcp >= 2.0 renamed McpError -> MCPError
    from mcp.shared.exceptions import MCPError as McpError
try:
    from mcp.shared.exceptions import NoBackChannelError
except ImportError:  # mcp < 2.0 has no back-channel concept (initialize() is always duplex)
    NoBackChannelError = ()  # `except ():` catches nothing
from mcp.types import (
    Completion,
    CompletionArgument,
)
from pydantic import BaseModel, Field

from qgis_mcp.client import QgisMCPClient
from qgis_mcp.helpers import (
    BATCH_BLOCKED_COMMANDS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    LLMS_CONTEXT_TEXT,
    TIMEOUT_DEFAULT,
    TIMEOUT_LONG,
    CommandTimeout,
    ToolError,
    code_failure_message,
    enrich_diagnose,
    make_layer_response,
    make_project_response,
    make_render_response,
)
from qgis_mcp.tools import ConnectivityToolset, ServerContext, register_toolsets
from qgis_mcp.tools.base import Context, FastMCP


def _setup_logging() -> logging.Logger:
    """Configure structured logging with stderr + optional rotating file handler."""
    _logger = logging.getLogger("QgisMCPServer")
    _logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # stderr handler at WARNING+ to keep MCP stdio transport clean
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(fmt)
    _logger.addHandler(stderr_handler)

    # File handler (configurable via env vars)
    _default_log_file = os.path.join("~", ".local", "share", "qgis-mcp", "server.log")
    log_file_raw = os.environ.get("QGIS_MCP_LOG_FILE", _default_log_file)
    log_level_name = os.environ.get("QGIS_MCP_LOG_LEVEL", "INFO").upper()
    file_level = getattr(logging, log_level_name, logging.INFO)

    if log_file_raw != "":
        log_file = os.path.expanduser(log_file_raw)
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file, maxBytes=5 * 1024 * 1024, backupCount=3, delay=True
            )
        except OSError as exc:
            _logger.setLevel(logging.WARNING)
            _logger.warning("Could not open log file %s: %s", log_file, exc)
        else:
            file_handler.setLevel(file_level)
            file_handler.setFormatter(fmt)
            _logger.addHandler(file_handler)
            # Set logger level to the minimum of both handler levels
            _logger.setLevel(min(logging.WARNING, file_level))
            _logger.info(f"Log file: {log_file}")
    else:
        _logger.setLevel(logging.WARNING)

    return _logger


logger = _setup_logging()


# ---------------------------------------------------------------------------
# Instance configuration
# ---------------------------------------------------------------------------

DEFAULT_INSTANCE = "default"
_INSTANCE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _parse_port(raw: str, context: str) -> int:
    """Parse and range-check a port number, reporting *context* on failure."""
    try:
        port = int(raw)
        if not 1 <= port <= 65535:
            raise ValueError("out of range")
    except ValueError as exc:
        raise ValueError(f"{context} must be an integer 1-65535, got: {raw!r}") from exc
    return port


def parse_instances(spec: str, default_host: str = DEFAULT_HOST) -> dict[str, tuple[str, int]]:
    """Parse a ``QGIS_MCP_INSTANCES`` string into ``{name: (host, port)}``.

    Format: comma-separated ``name=port`` or ``name=host:port`` entries, e.g.
    ``default=9878,b=9879`` or ``lab=192.168.1.5:9878``. Instance names match
    ``[A-Za-z0-9_-]+``. Entries without a host use *default_host* (which the
    caller takes from ``QGIS_MCP_HOST``). Insertion order is preserved.
    """
    instances: dict[str, tuple[str, int]] = {}
    for raw_entry in spec.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        name, sep, target = entry.partition("=")
        name = name.strip()
        target = target.strip()
        if not sep or not target:
            raise ValueError(
                "QGIS_MCP_INSTANCES entries must be 'name=port' or 'name=host:port', "
                f"got: {entry!r}"
            )
        if not _INSTANCE_NAME_RE.match(name):
            raise ValueError(
                f"QGIS_MCP_INSTANCES instance name must match [A-Za-z0-9_-]+, got: {name!r}"
            )
        if name in instances:
            raise ValueError(f"QGIS_MCP_INSTANCES has a duplicate instance name: {name!r}")
        if ":" in target:
            host, _, port_raw = target.rpartition(":")
            host = host.strip() or default_host
        else:
            host, port_raw = default_host, target
        port = _parse_port(port_raw.strip(), f"QGIS_MCP_INSTANCES port for {name!r}")
        instances[name] = (host, port)
    if not instances:
        raise ValueError("QGIS_MCP_INSTANCES is set but lists no instances")
    return instances


def get_instances() -> dict[str, tuple[str, int]]:
    """Resolve the configured QGIS instances from the environment.

    When ``QGIS_MCP_INSTANCES`` is unset or empty, exactly one instance named
    ``default`` is defined from ``QGIS_MCP_HOST``/``QGIS_MCP_PORT`` - so
    single-instance setups behave exactly as before. Read on every call (rather
    than cached at import) so the environment stays the single source of truth.
    """
    default_host = os.environ.get("QGIS_MCP_HOST", DEFAULT_HOST)
    spec = os.environ.get("QGIS_MCP_INSTANCES", "").strip()
    if spec:
        return parse_instances(spec, default_host)
    port = _parse_port(os.environ.get("QGIS_MCP_PORT", str(DEFAULT_PORT)), "QGIS_MCP_PORT")
    return {DEFAULT_INSTANCE: (default_host, port)}


def _unknown_instance_error(name: str, instances: dict[str, tuple[str, int]]) -> ValueError:
    """Build the error raised for an instance name that is not configured."""
    valid = ", ".join(instances) or "(none)"
    return ValueError(f"Unknown QGIS instance: {name!r}. Configured instances: {valid}")


def implicit_instance(instances: dict[str, tuple[str, int]]) -> str:
    """The instance a call with no explicit name is routed to.

    ``default`` when it exists, otherwise the FIRST configured entry - dict
    insertion order, which is the order written in ``QGIS_MCP_INSTANCES``.
    Without this fallback the natural config ``a=9878,b=9879`` would break every
    instance-less call, and instance-less is how tools are overwhelmingly
    invoked; requiring one entry to be literally named ``default`` is a trap
    rather than a safeguard.
    """
    if DEFAULT_INSTANCE in instances:
        return DEFAULT_INSTANCE
    return next(iter(instances))


def resolve_instance(instance: str | None) -> str:
    """Validate an instance name; ``None`` resolves per :func:`implicit_instance`."""
    instances = get_instances()
    if not instances:
        raise ValueError("No QGIS instances configured - check QGIS_MCP_INSTANCES")
    name = instance or implicit_instance(instances)
    if name not in instances:
        raise _unknown_instance_error(name, instances)
    return name


# ---------------------------------------------------------------------------
# Persistent connection management (one pooled connection per instance)
# ---------------------------------------------------------------------------

_qgis_connections: dict[str, QgisMCPClient] = {}
_connection_validated_at: dict[str, float] = {}
_CONNECTION_TTL: float = 5.0  # seconds between getpeername() validations
# One lock per instance: concurrent asyncio.to_thread calls to the SAME instance
# must not interleave frames on its shared socket, but two instances have
# separate sockets and must not serialize against each other.
_qgis_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()  # guards creation of entries in _qgis_locks


def _get_instance_lock(instance: str) -> threading.Lock:
    """Return the socket lock for *instance*, creating it on first use."""
    with _locks_guard:
        lock = _qgis_locks.get(instance)
        if lock is None:
            lock = threading.Lock()
            _qgis_locks[instance] = lock
        return lock


def get_qgis_connection(instance: str = DEFAULT_INSTANCE) -> QgisMCPClient:
    """Get or create the persistent QGIS connection for *instance*.

    Uses a TTL cache for connection validation: getpeername() is only
    called at most once per _CONNECTION_TTL seconds, avoiding a syscall
    on every tool invocation. The TTL is tracked per instance.
    """
    conn = _qgis_connections.get(instance)
    if conn is not None:
        now = time.monotonic()
        if now - _connection_validated_at.get(instance, 0.0) < _CONNECTION_TTL:
            return conn
        try:
            conn.socket.getpeername()
            _connection_validated_at[instance] = now
            return conn
        except Exception:
            logger.warning(
                "Existing connection to instance %r is no longer valid, reconnecting", instance
            )
            with contextlib.suppress(Exception):
                conn.disconnect()
            _qgis_connections.pop(instance, None)
            _connection_validated_at.pop(instance, None)

    instances = get_instances()
    if instance not in instances:
        raise _unknown_instance_error(instance, instances)
    host, port = instances[instance]

    conn = QgisMCPClient(host=host, port=port)
    if not conn.connect():
        # Chain the underlying error so _send_sync can tell a refusal (nothing
        # listening, retrying is pointless) from a timeout (host may be slow).
        raise ConnectionError(
            f"Could not connect to QGIS instance {instance!r} at {host}:{port}. "
            "Make sure the QGIS plugin is running."
        ) from conn.last_error
    _qgis_connections[instance] = conn
    _connection_validated_at[instance] = time.monotonic()
    logger.info(f"Created new persistent connection to QGIS instance {instance!r} at {host}:{port}")
    return conn


def _probe_instance(instance: str, host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True when *instance* currently accepts a socket connection.

    Always a fresh short-timeout TCP connection, closed immediately. The pooled
    socket cannot answer this: getpeername() keeps reporting the address after
    the peer has gone away, so a closed QGIS window would still read as
    reachable. Deliberately not _send_sync(): its first-connect retry schedule
    would make listing a single unreachable instance take ~11s.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Helper: send command, unwrap envelope, raise on error
# ---------------------------------------------------------------------------


def _invalidate_connection(instance: str = DEFAULT_INSTANCE) -> None:
    """Force-close the cached connection for *instance* so the next call reconnects."""
    conn = _qgis_connections.pop(instance, None)
    if conn is not None:
        with contextlib.suppress(Exception):
            conn.disconnect()
    _connection_validated_at.pop(instance, None)


_CONNECTION_ERRORS = (OSError, ConnectionError)
_MAX_RETRIES = 3
_RETRY_DELAYS = (0.5, 1.0)  # seconds between retries (last retry has no delay after)
# First-connect retries: more patient since QGIS/plugin may still be starting
_FIRST_CONNECT_RETRIES = 5
_FIRST_CONNECT_DELAYS = (1.0, 2.0, 3.0, 5.0)  # escalating backoff
_first_connected: set[str] = set()  # instance names that have connected at least once


def _is_refusal(exc: Exception) -> bool:
    """True when the host actively refused, i.e. nothing is listening on that port.

    get_qgis_connection() chains the client's error, so check the cause as well as
    the exception itself.
    """
    return isinstance(exc, ConnectionRefusedError) or isinstance(
        exc.__cause__, ConnectionRefusedError
    )


def _retry_schedule(retries: int | None) -> tuple[int, list[float]]:
    """Return (attempts, delays) for a send: see _send_sync for the reasoning."""
    if retries is not None:
        return max(1, retries), _RETRY_DELAYS
    if _first_connected:
        return _MAX_RETRIES, _RETRY_DELAYS
    return _FIRST_CONNECT_RETRIES, _FIRST_CONNECT_DELAYS


def _handle_send_error(
    exc: Exception,
    command_type: str,
    name: str,
    attempt: int,
    max_retries: int,
    delays: tuple[float, ...],
) -> None:
    """Handle socket/timeout errors inside _send_sync: wait before retry or re-raise."""
    _invalidate_connection(name)
    if isinstance(exc, CommandTimeout):
        # QGIS has the command and is still working on it; only the
        # response was abandoned. Retrying would run it a second
        # time: the layer added twice, the file written twice. A slow
        # *connect* is a plain ConnectionError from
        # get_qgis_connection() and does keep its retries.
        logger.warning(
            "Command %r timed out on instance %r - not retrying (%s)",
            command_type,
            name,
            exc,
        )
        raise exc
    if _first_connected and _is_refusal(exc):
        # The host answered: nothing is listening on that port. Another
        # instance has already connected, so this is a closed QGIS
        # window rather than a slow start, and retrying only repeats
        # the OS's ~2s refusal latency. Fail on the first attempt.
        logger.warning("Instance %r refused the connection - not retrying (%s)", name, exc)
        raise exc
    if attempt < max_retries - 1:
        delay = delays[min(attempt, len(delays) - 1)]
        logger.warning(
            "Connection error on instance %r (%s), retrying in %.1fs (attempt %d/%d)",
            name,
            exc,
            delay,
            attempt + 1,
            max_retries,
        )
        time.sleep(delay)
    else:
        logger.error(
            "Connection to instance %r failed after %d attempts: %s",
            name,
            max_retries,
            exc,
        )
        raise exc


def _send_sync(
    command_type: str,
    params: dict | None = None,
    timeout: int = TIMEOUT_DEFAULT,
    instance: str | None = None,
    retries: int | None = None,
) -> dict:
    """Send a command synchronously to *instance* and return the unwrapped result.

    ``instance=None`` resolves per :func:`implicit_instance` - the entry named
    ``default`` when present, otherwise the first one configured. Holds that
    instance's lock for the entire send+recv cycle so that concurrent
    asyncio.to_thread calls cannot interleave frames on its shared socket; other
    instances are unaffected.

    Retries on connection/socket errors with increasing delays. The patient
    schedule applies only while ``_first_connected`` is empty: nothing has
    answered yet, so QGIS or the plugin may still be starting and waiting is
    right. Once any instance has connected the stack is demonstrably up, so an
    unreachable instance is a closed window rather than a slow start and the
    short schedule applies.

    ``retries`` overrides that schedule. Pass 1 for calls that must stay quick.
    """
    name = resolve_instance(instance)
    last_exc: Exception | None = None
    max_retries, delays = _retry_schedule(retries)

    with _get_instance_lock(name):
        for attempt in range(max_retries):
            try:
                qgis = get_qgis_connection(name)
                result = qgis.send_command(command_type, params, timeout=timeout)
                _first_connected.add(name)
                break
            except _CONNECTION_ERRORS as exc:
                last_exc = exc
                _handle_send_error(exc, command_type, name, attempt, max_retries, delays)
        else:
            raise last_exc  # type: ignore[misc]  # unreachable, but satisfies type checker

    if not result or result.get("status") == "error":
        raise ToolError(result.get("message", "Command failed") if result else "No response")
    return result.get("result", {})


def _get_error_hint(message: str) -> str | None:
    """Return a helpful hint based on common QGIS/MCP error messages."""
    msg = message.lower()
    if "not found" in msg and "layer" in msg:
        return "Try calling 'get_layers' to see all valid layer IDs."
    if "field" in msg and "not found" in msg:
        return "Check the layer schema using 'qgis://layers/{layer_id}/schema'."
    if "crs" in msg or "projection" in msg:
        return "Verify CRS strings (e.g., 'EPSG:4326') or use 'transform_coordinates'."
    if "connection" in msg or "refused" in msg:
        return "Ensure the QGIS MCP plugin is started (Plugins > QGIS MCP > Start Server)."
    if "timeout" in msg:
        return "The operation took too long. For large renders or processing, this is expected."
    return None


async def _send(
    command_type: str,
    params: dict | None = None,
    timeout: int = TIMEOUT_DEFAULT,
    instance: str | None = None,
    retries: int | None = None,
) -> dict:
    """Send a command via asyncio.to_thread to avoid blocking the event loop."""
    try:
        return await asyncio.to_thread(_send_sync, command_type, params, timeout, instance, retries)
    except ToolError:
        raise
    except Exception as exc:
        # mcp >= 2.1 masks every non-ToolError to "Error executing tool <name>", so
        # a bad instance name or a dropped socket would reach the user as nothing.
        message = str(exc) or type(exc).__name__
        hint = _get_error_hint(message)
        if hint:
            logger.warning(f"Error hint added for: {message}")
            raise ToolError(f"{message}\n\nHINT: {hint}") from exc
        raise ToolError(message) from exc


# ---------------------------------------------------------------------------
# Helper: elicit confirmation for destructive operations
# ---------------------------------------------------------------------------


class _ConfirmSchema(BaseModel):
    """Response schema for destructive-operation confirmation."""

    confirm: bool = Field(description="Confirm this operation")


async def _confirm_destructive(ctx: Context, message: str) -> bool:
    """Ask user for confirmation before destructive operation.

    Returns True if client doesn't support elicitation (fail-open), since
    the tool is already marked destructive via ToolAnnotations and the client
    can gate execution at the tool-call level. Raises ToolError if the
    request could not be delivered at all (fail-closed) - client capability is
    unknown in that case, so proceeding would silently defeat the confirmation
    gate the caller explicitly opted into.

    Skipped by default: MCP clients gate destructive tool calls themselves
    (helped by the destructiveHint annotation), so eliciting here is a second
    prompt for the same call - and two prompts train click-through, which makes
    the client's own prompt worse. Set ``QGIS_MCP_AUTO_CONFIRM=0`` (or false/no/
    off) to elicit anyway, for a client that runs tools unattended. Read per
    call so a long-lived server honors changes.
    """
    if os.environ.get("QGIS_MCP_AUTO_CONFIRM", "").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }:
        return True
    try:
        response = await ctx.elicit(message=message, schema=_ConfirmSchema)
    except NoBackChannelError as e:
        # The client may well support elicitation - this connection just has no
        # channel for server-initiated requests (protocol 2026-07-28 per-request
        # dispatch, stateless or JSON-response streamable HTTP). We were never
        # able to ask, so - unlike genuine "client doesn't support elicitation" -
        # fail closed: QGIS_MCP_AUTO_CONFIRM=0 means the operator wants a gate.
        raise ToolError(
            "Cannot confirm destructive operation: this connection has no "
            "back-channel for server-initiated requests, so the confirmation "
            "prompt cannot be sent. Unset QGIS_MCP_AUTO_CONFIRM to rely on the "
            "client's own destructive-tool gate instead."
        ) from e
    except McpError:
        # Client doesn't support elicitation - proceed (fail-open).
        # The destructive ToolAnnotations hint lets clients gate at call time.
        # Only McpError is caught: a malformed elicit() call must not read as
        # "unsupported" and silently skip every confirmation (#27).
        logger.info("Elicitation not supported by client, proceeding with operation")
        return True
    return response.action == "accept" and bool(response.data and response.data.confirm)


# ---------------------------------------------------------------------------
# Server lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage server startup and shutdown lifecycle.

    Uses lazy connection: does NOT connect to QGIS on startup.
    The first tool call triggers connection via _send_sync()'s retry loop,
    which is more robust (handles QGIS still starting, plugin not yet enabled).
    """
    try:
        targets = ", ".join(f"{n}={h}:{p}" for n, (h, p) in get_instances().items())
    except ValueError as exc:
        # Don't fail startup on a bad config - surface it on the first tool call,
        # matching the previous behaviour for an invalid QGIS_MCP_PORT.
        targets = f"<invalid instance configuration: {exc}>"
    logger.info(f"QgisMCPServer starting up (will connect on first call to: {targets})")
    try:
        yield {}
    finally:
        for name in list(_qgis_connections):
            logger.info(f"Disconnecting from QGIS instance {name!r} on shutdown")
            _invalidate_connection(name)
        logger.info("QgisMCPServer shut down")


mcp = FastMCP(
    name="LuiccianQgisMcp",
    instructions="QGIS integration through the Model Context Protocol. "
    "Use tools for actions, resources for read-only data, prompts for workflows.",
    lifespan=server_lifespan,
)


# ---------------------------------------------------------------------------
# Resource Cache for large results
# ---------------------------------------------------------------------------

_CACHE_MAX_ENTRIES = 32
# Bounded and ordered: entries are never read back in most sessions, so an
# unbounded dict would hold every large result until the process exits.
_resource_cache: OrderedDict[str, str] = OrderedDict()


def _cache_as_resource(data: Any) -> str:
    """Generate a random ID, store data as JSON, and return a URI."""
    cache_id = secrets.token_hex(8)
    _resource_cache[cache_id] = json.dumps(data)
    while len(_resource_cache) > _CACHE_MAX_ENTRIES:
        _resource_cache.popitem(last=False)
    return f"qgis://cache/{cache_id}"


@mcp.resource("qgis://cache/{cache_id}", name="cached_resource", description="Cached large result")
def cached_resource(cache_id: str) -> str:
    """Register an MCP resource handler for cached data."""
    if cache_id not in _resource_cache:
        raise ToolError(f"Cache ID not found: {cache_id}")
    return _resource_cache[cache_id]


# ===========================================================================
# MCP TOOLS
# ===========================================================================


async def _send_proxy(*args, **kwargs):
    return await _send(*args, **kwargs)


_server_context = ServerContext(
    mcp=mcp,
    send=_send_proxy,
    confirm_destructive=lambda *a, **kw: _confirm_destructive(*a, **kw),
    cache_as_resource=_cache_as_resource,
    probe_instance=lambda *a, **kw: _probe_instance(*a, **kw),
    get_instances=get_instances,
    implicit_instance=implicit_instance,
    enrich_diagnose=enrich_diagnose,
    make_layer_response=make_layer_response,
    make_project_response=make_project_response,
    make_render_response=make_render_response,
    timeout_long=TIMEOUT_LONG,
    batch_blocked_commands=BATCH_BLOCKED_COMMANDS,
    code_failure_message=code_failure_message,
    logger=logger,
)
_registered_toolsets = register_toolsets(_server_context)

_instance_identity = next(
    toolset.instance_identity
    for toolset in _registered_toolsets
    if isinstance(toolset, ConnectivityToolset)
)

for _tool_name, _tool_obj in mcp._tool_manager._tools.items():
    globals().setdefault(_tool_name, _tool_obj.fn)


# ---------------------------------------------------------------------------
# Compound tool mode (opt-in via QGIS_MCP_TOOL_MODE=compound)
# ---------------------------------------------------------------------------

_tool_mode = os.environ.get("QGIS_MCP_TOOL_MODE", "granular")
if _tool_mode == "compound":
    # Compound tools carry no `instance` parameter, so every call would silently
    # go to the implicit instance while multi-instance config suggested
    # otherwise - a wrong-instance write with no error is worse than refusing to
    # start. Refuse the unsupported combination instead; single-instance
    # compound mode is unaffected.
    _compound_instances = get_instances()
    if len(_compound_instances) > 1:
        raise SystemExit(
            "QGIS_MCP_TOOL_MODE=compound does not support multiple instances "
            f"(QGIS_MCP_INSTANCES defines {len(_compound_instances)}: "
            f"{', '.join(_compound_instances)}). Compound tools cannot select an "
            "instance, so every call would silently target "
            f"{implicit_instance(_compound_instances)!r}. Use granular mode for "
            "multi-instance setups, or configure a single instance."
        )

    from qgis_mcp.compound_tools import register_compound_tools

    # Replace granular tools with compound tools
    mcp._tool_manager._tools.clear()
    register_compound_tools(mcp, _send, _confirm_destructive)
    logger.info(f"Compound tool mode: {len(mcp._tool_manager._tools)} tools registered")


def _strip_schema_titles() -> None:
    """Drop redundant auto-generated 'title' keys from tool input schemas.

    Pydantic adds a display 'title' to the schema and every property (e.g. the
    param ``layer_id`` gets ``"title": "Layer Id"``) that just restates the name.
    It is sent to the client on every turn but carries no information, so removing
    it trims ~2k tokens off the granular tool schema with no behavior change.
    """

    def clean(node: object) -> None:
        if isinstance(node, dict):
            node.pop("title", None)
            for key in ("properties", "$defs", "definitions"):
                for sub in node.get(key, {}).values():
                    clean(sub)
            for key in ("items", "additionalProperties"):
                if isinstance(node.get(key), dict):
                    clean(node[key])
            for key in ("anyOf", "allOf", "oneOf"):
                for sub in node.get(key, []):
                    clean(sub)

    for tool in mcp._tool_manager._tools.values():
        clean(tool.parameters)


def _strip_instance_param() -> None:
    """Drop the ``instance`` property from tool schemas when only one exists.

    With a single instance there is nothing to route, so advertising ``instance``
    on every tool is pure overhead: it grows the tool list sent on every turn by
    ~17% (45.8k -> 53.7k chars) for the majority of users, who run one QGIS. The
    Python parameter stays and keeps defaulting to None, which resolves to that
    single instance, so behaviour is identical - only the advertised schema
    shrinks. Restored as soon as a second instance is configured.

    Same mechanism as _strip_schema_titles() above, and applied after it.
    """
    try:
        if len(get_instances()) > 1:
            return
    except ValueError:
        # An invalid configuration surfaces on the first tool call, as in the
        # lifespan handler - don't decide anything here.
        return

    for tool in mcp._tool_manager._tools.values():
        properties = tool.parameters.get("properties")
        if properties:
            properties.pop("instance", None)


_strip_schema_titles()
_strip_instance_param()


# ===========================================================================
# MCP COMPLETIONS
# ===========================================================================

_completion_cache: list[str] = []
_completion_cache_at: float = 0.0
_COMPLETION_TTL: float = 10.0  # seconds - avoids hitting QGIS on every keystroke


@mcp.completion()
async def handle_completion(ref, argument: CompletionArgument, context=None):
    """Auto-complete layer_id arguments with available layer IDs.

    Uses a TTL cache to avoid querying QGIS on every keystroke.
    """
    global _completion_cache, _completion_cache_at

    if argument.name == "layer_id":
        try:
            now = time.monotonic()
            if now - _completion_cache_at >= _COMPLETION_TTL or not _completion_cache:
                result = await _send("get_layers", {"limit": 200, "offset": 0})
                layers = result.get("layers", [])
                _completion_cache = [
                    layer["id"]
                    for layer in layers
                    if isinstance(layer, dict) and isinstance(layer.get("id"), str)
                ]
                _completion_cache_at = now
            ids = _completion_cache
            if argument.value:
                prefix = argument.value.lower()
                ids = [lid for lid in ids if prefix in lid.lower()]
            return Completion(values=ids[:50])
        except Exception:
            return None
    return None


# ===========================================================================
# MCP RESOURCES
# ===========================================================================


# Resource URIs carry no instance segment, so all of these read the implicit
# instance. With several instances configured that is a silent choice, so each
# description says which one it reads and points at the tool for the rest.
_IMPLICIT = " (implicit instance - use the equivalent tool with instance= for another)"


@mcp.resource(
    "qgis://info",
    name="qgis_info",
    description="QGIS version, profile, and plugin count" + _IMPLICIT,
)
async def qgis_info_resource() -> str:
    return json.dumps(await _send("get_qgis_info"))


@mcp.resource(
    "qgis://project",
    name="project_info",
    description="Current project metadata, CRS, layer count, layer summary" + _IMPLICIT,
)
async def project_info_resource() -> str:
    return json.dumps(await _send("get_project_info"))


@mcp.resource(
    "qgis://layers",
    name="layer_list",
    description="All layers with IDs, names, types, visibility" + _IMPLICIT,
)
async def layers_resource() -> str:
    return json.dumps(await _send("get_layers"))


@mcp.resource(
    "qgis://layers/{layer_id}/info",
    name="layer_info",
    description="Detailed layer info: CRS, extent, fields, feature count, source, provider"
    + _IMPLICIT,
)
async def layer_info_resource(layer_id: str) -> str:
    return json.dumps(await _send("get_layer_info", {"layer_id": layer_id}))


@mcp.resource(
    "qgis://layers/{layer_id}/features",
    name="layer_features",
    description="Sample features (first 10) from a vector layer" + _IMPLICIT,
)
async def layer_features_resource(layer_id: str) -> str:
    return json.dumps(await _send("get_layer_features", {"layer_id": layer_id, "limit": 10}))


@mcp.resource(
    "qgis://layers/{layer_id}/schema",
    name="layer_schema",
    description="Field names, types, and lengths for a vector layer" + _IMPLICIT,
)
async def layer_schema_resource(layer_id: str) -> str:
    return json.dumps(await _send("get_layer_schema", {"layer_id": layer_id}))


@mcp.resource(
    "qgis://llms.txt",
    name="llms_context",
    description="Capabilities summary for LLM context - lists all tools, resources, and usage tips",
)
def llms_context_resource() -> str:
    return LLMS_CONTEXT_TEXT


# ===========================================================================
# MCP PROMPTS
# ===========================================================================


@mcp.prompt(
    name="analyze_layer",
    description="Deeply inspect a layer's schema, sample data, and compute detailed field statistics",
)
def analyze_layer_prompt(layer_id: str) -> list[UserMessage]:
    return [
        UserMessage(
            content=f"Perform a comprehensive analysis of the layer with ID '{layer_id}':\n"
            f"1. Read resource qgis://layers/{layer_id}/info for general metadata (CRS, extent, count)\n"
            f"2. Read resource qgis://layers/{layer_id}/schema to understand field types and constraints\n"
            f"3. Read resource qgis://layers/{layer_id}/features to inspect representative sample data\n"
            f"4. For each numeric field, call get_field_statistics to understand the data distribution (min, max, mean, etc.)\n"
            f"5. For categorical fields, identify unique values and their prevalence\n"
            f"6. Provide a detailed summary including: geometry validity, projection suitability, data quality, and potential analysis use cases"
        )
    ]


@mcp.prompt(
    name="spatial_analysis",
    description="Run a spatial operation between two layers with CRS validation",
)
def spatial_analysis_prompt(
    input_layer: str, overlay_layer: str, operation: str
) -> list[UserMessage]:
    return [
        UserMessage(
            content=f"Perform a spatial {operation} between layers:\n"
            f"- Input: {input_layer}\n"
            f"- Overlay: {overlay_layer}\n"
            f"Steps:\n"
            f"1. Get info for both layers (get_layers or qgis://layers/ID/info)\n"
            f"2. Verify both layers are vector layers with compatible geometry types\n"
            f"3. Check that CRS matches; if not, reproject one layer first\n"
            f"4. Use execute_processing with the appropriate algorithm (e.g. native:intersection, native:union)\n"
            f"5. Report the result layer's feature count and fields"
        )
    ]


@mcp.prompt(
    name="create_processing_model",
    description="Translate a natural-language workflow description into a saved QGIS Processing Model",
)
def create_processing_model_prompt(description: str) -> list[UserMessage]:
    return [
        UserMessage(
            content=(
                "Build a QGIS Processing Model that implements this workflow:\n\n"
                f'"{description}"\n\n'
                "Call the `create_processing_model` tool ONCE. Algorithm lookup and parameter "
                "validation happen inside the plugin against QGIS's Processing registry - do NOT "
                "call `list_processing_algorithms` or `get_algorithm_help`. For each step pass a "
                "concise `algorithm` keyword (e.g. 'buffer', 'centroids', 'clip') or a full id; "
                "if a keyword is ambiguous the tool returns the candidate list so you can retry "
                "with a more specific hint. Reference model inputs as '@name', earlier step "
                "outputs as '$step_id.OUTPUT', and QGIS expressions as '=expr'. "
                "The model is always saved into the QGIS user models folder and registered in the "
                "Processing Toolbox; if the requested name is taken the tool appends a numeric "
                "suffix and returns the actual filename used. "
                "After the call, summarize the resolved_steps it returned and tell the user the "
                "final model name so they can find it in the toolbox."
            )
        )
    ]


@mcp.prompt(
    name="style_map", description="Create a thematic map with categorized or graduated symbology"
)
def style_map_prompt(layer_id: str, field: str) -> list[UserMessage]:
    return [
        UserMessage(
            content=f"Style layer '{layer_id}' based on field '{field}':\n"
            f"1. Get the layer schema and sample data to understand the field values\n"
            f"2. Call get_field_statistics for '{field}' to understand the data distribution\n"
            f"3. If the field is categorical, use set_layer_style with style_type='categorized'\n"
            f"4. If the field is numeric, use set_layer_style with style_type='graduated'\n"
            f"5. Refresh the canvas and render a preview image with render_map"
        )
    ]


# ===========================================================================
# Entry point
# ===========================================================================


def main():
    transport = os.environ.get("QGIS_MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
