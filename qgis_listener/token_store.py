"""The shared token file, read by the plugin and written by its UI.

One token for both halves of the setup. The MCP server (``qgis_mcp``)
and the plugin (``qgis_listener``) each ship their own copy of this module -
they are installed by different mechanisms and cannot import each other - so
the two files must stay identical apart from their docstrings. A test pins the
shared constants.

Resolution order is the environment first, then the file, then no auth:

- ``QGIS_MCP_TOKEN`` set and non-empty after stripping wins. Unchanged from
  upstream, so an existing deployment keeps working without touching the UI.
- Otherwise the token file. Its directory is per-user, so one file covers one
  user's QGIS and every MCP client they configure.
- Otherwise auth is off.

Stdlib only and free of ``qgis`` imports, like :mod:`wire` and :mod:`constants`,
and must stay Python 3.9-compatible.
"""

import contextlib
import os
import secrets
from pathlib import Path

# The environment variable both halves read. Same name as upstream: a rename
# would silently disable auth for everyone who already set it.
ENV_VAR = "QGIS_MCP_TOKEN"

# One directory under the user's config root, shared by every QGIS profile on
# the machine and by the MCP server.
APP_DIR_NAME = "qgis-mcp"

TOKEN_FILENAME = "token"  # noqa: S105 - filename, not a credential

_MIN_TOKEN_BYTES = 32


def _config_root():
    """The per-user configuration root.

    Windows uses ``%APPDATA%`` (Roaming), falling back to the same place under
    the home directory when the variable is missing. Everywhere else honours
    ``$XDG_CONFIG_HOME`` and defaults to ``~/.config``.
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata)
        return Path.home() / "AppData" / "Roaming"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def token_path():
    """Where the token file lives, whether or not it exists."""
    return str(_config_root() / APP_DIR_NAME / TOKEN_FILENAME)


def _env_token():
    return os.environ.get(ENV_VAR, "").strip()


def _file_token():
    try:
        path = token_path()
    except RuntimeError:
        # Path.home() cannot resolve the home directory (a stripped
        # environment); treat it like a missing file rather than raising, since
        # this runs on the path of every command.
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def read_token():
    """The token in force, or None when auth is off."""
    token = _env_token()
    if token:
        return token
    token = _file_token()
    return token or None


def generate_token():
    """A fresh random token: URL-safe, so it pastes anywhere unchanged."""
    return secrets.token_urlsafe(_MIN_TOKEN_BYTES)


def write_token(token):
    """Persist ``token`` and return its path, replacing any previous token.

    Written to a sibling temp file and renamed into place, so a reader never
    sees a half-written token and a failure leaves the old one intact. The temp
    file is created 0600, which ``os.replace`` carries over to the token file.
    """
    path = token_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
    return path


def revoke_token():
    """Delete the token file. True when there was one, False when there was not."""
    try:
        os.remove(token_path())
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True


def token_status():
    """What the UI needs to describe the current state.

    ``source`` says where ``token`` came from: the environment, the file, or
    nowhere. ``token`` is the value itself, so the UI can offer to copy it.
    """
    env_token = _env_token()
    if env_token:
        source, token = "env", env_token
    else:
        file_token = _file_token()
        source, token = ("file", file_token) if file_token else ("none", None)
    try:
        path = token_path()
    except RuntimeError:
        path = ""
    return {
        "active": bool(token),
        "source": source,
        "path": path,
        "token": token,
    }
