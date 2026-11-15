#!/usr/bin/env python3
"""
QGIS MCP Client - Simple client to connect to the QGIS MCP server.

Uses length-prefixed framing: each message is preceded by a 4-byte
big-endian unsigned int indicating the JSON payload size in bytes.
"""

import contextlib
import json
import logging
import socket

from qgis_mcp.protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    HEADER_STRUCT,
    MAX_MESSAGE_SIZE,
    RECV_CHUNK_SIZE,
    TIMEOUT_DEFAULT,
    CommandTimeout,
    get_auth_token,
    get_client_version,
    get_install_info,
)

logger = logging.getLogger("QgisMCPClient")

# Cap the TCP handshake. Without it connect() inherits the OS default, so a host
# that routes but has nothing listening (easy to configure now that instances
# carry their own host) stalls ~21s per attempt - times the retry schedule, that
# is minutes for one tool call. A local refusal is immediate either way.
_CONNECT_TIMEOUT = 3.0


class QgisMCPClient:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.socket = None
        self._current_timeout = None  # Track timeout to skip redundant syscalls
        # Why the last connect() failed. Callers need the distinction: a refusal
        # means nothing is listening and retrying cannot help, while a timeout
        # may just be a slow host.
        self.last_error = None

    def connect(self, timeout=_CONNECT_TIMEOUT):
        try:
            # create_connection resolves both IPv4 and IPv6 ("::1"), like _probe_instance.
            self.socket = socket.create_connection((self.host, self.port), timeout=timeout)
            # Disable Nagle's algorithm: send small packets immediately instead
            # of waiting up to 40ms to coalesce. Our request payloads are small
            # (typically <1KB) and we always want them sent without delay.
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.settimeout(None)  # back to blocking; send_command sets its own
            self._current_timeout = None
            self.last_error = None
            return True
        except Exception as exc:
            # Not logger.exception: a probe of a closed instance is routine, and a
            # full traceback per retry per instance buries the actual failure.
            logger.warning("Could not connect to %s:%s (%s)", self.host, self.port, exc)
            self.last_error = exc
            if self.socket is not None:
                with contextlib.suppress(OSError):
                    self.socket.close()
                self.socket = None
            return False

    def disconnect(self):
        if self.socket:
            self.socket.close()
            self.socket = None
            self._current_timeout = None

    # The plugin refuses to frame anything larger, so a bigger cap here would
    # only describe messages that cannot arrive.
    _MAX_RESPONSE_SIZE = MAX_MESSAGE_SIZE

    def _recv_exact(self, n):
        """Read exactly n bytes from the socket.

        Uses a pre-allocated buffer with recv_into() to avoid intermediate
        copies from bytearray.extend(). The benefit is reduced p99 latency
        variance for large payloads (5MB+), though median throughput is
        similar to the extend approach on loopback.
        """
        if n > self._MAX_RESPONSE_SIZE:
            raise ValueError(f"Response too large: {n} bytes (max {self._MAX_RESPONSE_SIZE})")
        buf = bytearray(n)
        view = memoryview(buf)
        pos = 0
        while pos < n:
            nbytes = self.socket.recv_into(view[pos:], min(n - pos, RECV_CHUNK_SIZE))
            if nbytes == 0:
                raise ConnectionError("Connection closed")
            pos += nbytes
        return bytes(buf)

    def _set_timeout(self, timeout):
        """Set socket timeout only when the value actually changes."""
        if self._current_timeout != timeout:
            self.socket.settimeout(timeout)
            self._current_timeout = timeout

    def _build_command_envelope(self, command_type, params=None):
        """Build the wire payload with client version metadata and optional auth token."""
        # The plugin reads `client_version` to warn on version drift between the
        # uvx cache and QGIS, and `client_install` to display the right update cmd.
        install_kind, install_root = get_install_info()
        command = {
            "type": command_type,
            "params": params or {},
            "client_version": get_client_version(),
            "client_install": install_kind,
        }
        if install_root:
            command["client_root"] = install_root

        # Read per command so token rotations take effect on the next call.
        token = get_auth_token()
        if token:
            command["token"] = token
        return command

    def _send_and_recv_frame(self, command, timeout):
        """Serialize, frame-send, and frame-read a single JSON command exchange."""
        data = json.dumps(command).encode("utf-8")
        header = HEADER_STRUCT.pack(len(data))
        # Arm the timeout before sends as well as reads so a stalled sendall raises TimeoutError.
        self._set_timeout(timeout)
        self.socket.sendall(header)
        self.socket.sendall(data)

        resp_header = self._recv_exact(4)
        resp_len = HEADER_STRUCT.unpack(resp_header)[0]
        resp_data = self._recv_exact(resp_len)

        self._set_timeout(None)
        return json.loads(resp_data)

    def send_command(self, command_type, params=None, timeout=TIMEOUT_DEFAULT):
        """Send a command over the connected socket and return the parsed JSON response."""
        if not self.socket:
            raise ConnectionError("Not connected to server")
        if timeout is not None and timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout!r}")

        command = self._build_command_envelope(command_type, params)
        try:
            return self._send_and_recv_frame(command, timeout)
        except TimeoutError as err:
            # Frame state is unrecoverable: close so the cache reconnects on the next call.
            logger.warning("Socket operation timed out after %ds", timeout)
            self.disconnect()
            raise CommandTimeout(f"Socket operation timed out after {timeout}s") from err
        except ValueError as err:
            self.disconnect()
            raise ConnectionError(
                f"Protocol framing error from {self.host}:{self.port}, connection reset. "
                "Whatever answered there does not speak the QGIS MCP protocol; another "
                "program may hold the port. Give the QGIS plugin its own port (the "
                "dropdown next to its toolbar button) and set QGIS_MCP_PORT to match."
            ) from err
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
            self.disconnect()
            raise  # Let callers handle reconnection
        except Exception as e:
            logger.exception("Error sending command")
            self.disconnect()
            raise ConnectionError(f"Send command failed: {e}") from e


def print_json(data):
    print(json.dumps(data, indent=2))


def main():
    client = QgisMCPClient()
    if not client.connect():
        logger.error("Could not connect to QGIS MCP server")
        return

    try:
        logger.info("Checking connection...")
        response = client.send_command("ping")
        if response and response.get("status") == "success":
            logger.info("Connected successfully")
        else:
            logger.error("Connection error")
            return

        print("\nQGIS Info:")
        print_json(client.send_command("get_qgis_info"))

        print("\nProject Info:")
        print_json(client.send_command("get_project_info"))

    except Exception:
        logger.exception("Error running commands")


if __name__ == "__main__":
    main()
