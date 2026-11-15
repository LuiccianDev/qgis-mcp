"""The "Configure MCP clients" dialog and the client-config registry it writes.

Knows where each supported MCP client keeps its config file and what a luiccian-qgis-mcp
server entry has to look like in it.
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from qgis.core import QgsApplication, QgsMessageLog, QgsSettings
from qgis.PyQt.QtCore import QSize, QTimer, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .compat import (
    ECHO_NORMAL,
    ECHO_PASSWORD,
    MSG_CRITICAL,
    MSG_INFO,
    MSGBOX_ACCEPT_ROLE,
    MSGBOX_QUESTION,
    MSGBOX_REJECT_ROLE,
    TEXT_SELECTABLE_BY_MOUSE,
)
from .constants import LOG_TAG, PLUGIN_DIR, REPO_URL, SETTINGS_PREFIX, plugin_version
from .token_store import (
    generate_token,
    read_token,
    revoke_token,
    token_path,
    token_status,
    write_token,
)

# Fallback for a drifted MCP server too old to announce its own update command.
# Assumes the recommended uvx install, where clearing the cache is what makes
# the next launch re-resolve the archive URL instead of reusing the old build.
DEFAULT_VERSION_FIX = "uv cache clean luiccian-qgis-mcp"


def write_json_atomic(path, data):
    """Write JSON to ``path`` through a temporary file, then rename it into place.

    These are the user's own MCP client configs. A write that dies partway (full
    disk, QGIS killed) would otherwise leave one truncated and unparseable, and
    the client would start with no servers at all.
    """
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def jsonc_to_json(text):
    """Strip JSONC comments and trailing commas while keeping strings verbatim."""
    stripped = re.sub(
        r'("(?:\\.|[^"\\])*")|/\*.*?\*/|//[^\n]*',
        lambda m: m.group(1) or "",
        text,
        flags=re.DOTALL,
    )
    return re.sub(r",\s*([}\]])", r"\1", stripped)


def read_jsonc(path):
    """Read a JSON or JSONC file into a dict, returning {} for missing/empty files."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = json.loads(jsonc_to_json(text))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path.name}")
    return data


def backup_config(path):
    """Copy an existing config file to a timestamped .bak-* file and return its path."""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    bak = path.with_suffix(f"{path.suffix}.bak-{stamp}")
    n = 0
    while bak.exists():
        n += 1
        bak = path.with_suffix(f"{path.suffix}.bak-{stamp}-{n}")
    shutil.copy2(path, bak)
    return bak


def has_qgis_entry(data, key):
    """Return True when *data* maps *key* to a dict containing 'qgis'."""
    return isinstance(data, dict) and isinstance(data.get(key), dict) and "qgis" in data[key]


def merge_qgis_entry(data, key, entry):
    """Insert or update ``data[key]['qgis'] = entry``, replacing non-dict sections."""
    if not isinstance(data.get(key), dict):
        data[key] = {}
    data[key]["qgis"] = entry


def _is_dev_checkout(repo_dir):
    """True when the plugin runs from a git clone rather than a Plugin Manager install."""
    return (repo_dir / ".git").exists()


def _client_config_registry(repo_dir):
    """Map client name -> {path, key} (or {print_only}) for MCP config files.

    Shared by the configurator dialog and the stale-config migration check.
    """
    home = Path.home()
    appdata = (
        Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        if sys.platform == "win32"
        else None
    )

    if sys.platform == "darwin":
        claude_cfg = (
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        )
    elif sys.platform == "win32":
        claude_cfg = appdata / "Claude" / "claude_desktop_config.json"
    else:
        claude_cfg = home / ".config" / "Claude" / "claude_desktop_config.json"

    antigravity_dir = Path(
        os.environ.get("ANTIGRAVITY_CONFIG_DIR", home / ".gemini" / "antigravity")
    )
    antigravity_cfg = antigravity_dir / "mcp_config.json"

    return {
        "antigravity": {"path": antigravity_cfg, "key": "mcpServers"},
        "claude-desktop": {"path": claude_cfg, "key": "mcpServers"},
        "claude-code": {"print_only": True, "entry_format": "claude_cli", "cli": "claude"},
        "manual": {
            "print_only": True,
            "entry_format": "manual",
            "hint": "Copy the JSON above into your MCP client's configuration file.",
        },
    }


def _qgis_entry_command_args(entry):
    """Return (command, args) for a 'qgis' server entry."""
    if not isinstance(entry, dict):
        return None, []
    cmd = entry.get("command")
    return cmd, entry.get("args", [])


def _qgis_entry_has_refresh(entry):
    """True when a remote uvx 'qgis' entry has --refresh-package (fails offline)."""
    command, args = _qgis_entry_command_args(entry)
    if command != "uvx" or "luiccian-qgis-mcp" not in args:
        return False  # local mode / unknown - leave alone
    return "--refresh-package" in args


def _remove_refresh_from_entry(entry):
    """Remove '--refresh-package luiccian-qgis-mcp' from a uvx 'qgis' entry.

    Only the flat command/args shape exists here - it is what
    ``_qgis_entry_has_refresh`` matched before this is called. Anything else in
    the user's config file is left alone rather than raising in the timer slot
    that calls this.
    """
    args = entry.get("args")
    if not isinstance(args, list):
        return entry
    try:
        idx = args.index("--refresh-package")
    except ValueError:
        return entry
    end = idx + 2  # the flag and its value
    del args[idx:end]
    return entry


class MCPConfiguratorDialog(QDialog):
    def __init__(self, iface, parent=None, server=None, start_server=None):
        super().__init__(parent)
        self.iface = iface
        # The running QgisMCPServer, when there is one: it knows which MCP server
        # versions have actually connected, which is the only way this dialog can
        # report drift between the two halves.
        self.server = server
        # Callable that starts the socket server and returns it (or None on
        # failure). Supplied by the plugin, which owns the toolbar state.
        self.start_server = start_server
        self.setWindowTitle("Luiccian QGIS Listener - Setup & Configurator")
        self.setMinimumSize(600, 500)

        self.repo_dir = Path(__file__).resolve().parent.parent
        # Zip archive instead of git+ URL: uvx then needs no git executable,
        # which is not visible to GUI-spawned MCP servers (e.g. Claude Desktop
        # on Windows).
        self.github_url = "https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/main.zip"

        self.init_ui()
        self.refresh_status()

    def _dialog_header(self):
        """Top row with plugin icon and title."""
        header = QHBoxLayout()
        header.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QIcon(os.path.join(PLUGIN_DIR, "icons", "icon.png")).pixmap(QSize(44, 44)))
        header.addWidget(logo)
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        heading = QLabel("Luiccian QGIS Listener")
        heading.setStyleSheet("font-size: 17px; font-weight: bold;")
        subtitle = QLabel("Connect your AI client to QGIS")
        subtitle.setStyleSheet("color: palette(mid);")
        title_col.addWidget(heading)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()
        return header

    def _client_group(self):
        """Step 1 group: AI client selector, launch mode, refresh and autostart options."""
        client_group = QGroupBox("1  ·  AI client")
        client_form = QVBoxLayout(client_group)
        client_form.setSpacing(8)

        client_row = QHBoxLayout()
        client_row.addWidget(QLabel("Client:"))
        self.client_combo = QComboBox()
        self.client_combo.addItems(["antigravity", "claude-code", "claude-desktop", "manual"])
        self.client_combo.setMinimumWidth(180)
        self.client_combo.currentTextChanged.connect(self._on_client_changed)
        client_row.addWidget(self.client_combo)

        # Mode selector - only relevant for dev installs with a local clone
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Remote (uvx - recommended)", "Local (uv run)"])
        self.mode_combo.setToolTip(
            "Remote: install MCP server on-the-fly via uvx (no clone needed).\n"
            "Local: run MCP server from your git clone via uv."
        )
        self.mode_combo.setVisible(self._is_dev_install())
        if self._is_dev_install():
            self.mode_combo.setCurrentIndex(1)
        self.mode_combo.currentTextChanged.connect(self._on_client_changed)
        client_row.addWidget(self.mode_combo)
        client_row.addStretch()
        client_form.addLayout(client_row)

        # Refresh toggle - adds `--refresh-package luiccian-qgis-mcp` so uvx re-pulls the
        # latest server from GitHub on every launch (remote mode only).
        self.refresh_check = QCheckBox("Always pull latest server from GitHub")
        self.refresh_check.setToolTip(
            "Add --refresh-package luiccian-qgis-mcp so uvx re-pulls the latest server from\n"
            "GitHub on every client launch (stays in sync with the plugin).\n"
            "Warning: requires network at launch - the server fails to start offline.\n"
            "Leave unchecked to use the cached version (works offline, manual updates)."
        )
        self.refresh_check.setChecked(False)
        self.refresh_check.toggled.connect(self._on_client_changed)
        client_form.addWidget(self.refresh_check)

        self.autostart_check = QCheckBox("Start MCP server automatically when QGIS opens")
        self.autostart_check.setToolTip(
            "Launch the MCP server on QGIS startup so an AI agent can reconnect\n"
            "without manually starting it (e.g. after a crash and restart).\n"
            "Ticking this also starts the server now if it is not running."
        )
        self.autostart_check.setChecked(
            QgsSettings().value(f"{SETTINGS_PREFIX}/autostart", False, type=bool)
        )
        self.autostart_check.toggled.connect(self._save_autostart)
        client_form.addWidget(self.autostart_check)

        # Whether the socket server is up. Without it, ticking auto-start looks
        # like nothing happened - the toolbar icon is hidden behind this dialog.
        self.server_label = QLabel()
        client_form.addWidget(self.server_label)
        return client_group

    def _preview_group(self):
        """Step 2 group: generated client snippet, copy action, status and version check."""
        preview_group = QGroupBox("2  ·  Configuration")
        preview_box = QVBoxLayout(preview_group)
        preview_box.setSpacing(6)

        self.preview_label = QLabel("Add to your client config file:")
        preview_box.addWidget(self.preview_label)

        preview_row = QHBoxLayout()
        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(160)
        self.preview_edit.setStyleSheet("font-family: monospace;")
        preview_row.addWidget(self.preview_edit)

        copy_col = QVBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setFixedWidth(64)
        self.copy_btn.clicked.connect(self._copy_preview)
        copy_col.addWidget(self.copy_btn)
        copy_col.addStretch()
        preview_row.addLayout(copy_col)
        preview_box.addLayout(preview_row)

        self.status_label = QLabel()
        preview_box.addWidget(self.status_label)

        # Plugin vs MCP server version. The two are installed and updated by
        # different mechanisms (Plugin Manager vs the uvx cache), so drift is
        # normal and invisible unless it is stated somewhere the user looks.
        self.version_label = QLabel()
        self.version_label.setWordWrap(True)
        # The drift message names a command to run; a plain QLabel cannot even be
        # selected, so give it both selection and a one-click copy.
        self.version_label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
        version_row = QHBoxLayout()
        version_row.addWidget(self.version_label, 1)
        self.version_fix_btn = QPushButton("Copy fix")
        self.version_fix_btn.setFixedWidth(80)
        self.version_fix_btn.clicked.connect(self._copy_version_fix)
        self.version_fix_btn.setVisible(False)
        version_row.addWidget(self.version_fix_btn)
        preview_box.addLayout(version_row)
        return preview_group

    def _action_row(self):
        """Bottom button bar: Apply Config, Open GitHub, Close."""
        action_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Config")
        self.apply_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #43A047; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self.apply_btn.clicked.connect(self.run_config)
        action_row.addWidget(self.apply_btn)
        action_row.addStretch()
        github_btn = QPushButton("Open GitHub")
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        action_row.addWidget(github_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        action_row.addWidget(close_btn)
        return action_row

    def init_ui(self):
        self.setStyleSheet(
            "QGroupBox {"
            "  font-weight: bold;"
            "  border: 1px solid palette(mid);"
            "  border-radius: 6px;"
            "  margin-top: 10px;"
            "  padding: 10px 10px 8px 10px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  left: 8px;"
            "  padding: 0 4px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addLayout(self._dialog_header())
        layout.addWidget(self._client_group())
        layout.addWidget(self._preview_group())
        layout.addWidget(self._token_group())
        layout.addStretch()
        layout.addLayout(self._action_row())

        self._refresh_token_state()

    def _token_group(self):
        """The shared-token group: status, value, copy, rotate and revoke.

        One token file, read by both halves of the setup, so a client config
        never carries the secret and rotating it needs no reconfiguration. The
        environment variable still wins when set, which the status line says and
        the buttons enforce.
        """
        group = QGroupBox("3  ·  Security")
        box = QVBoxLayout(group)
        box.setSpacing(6)

        self.token_status_label = QLabel()
        self.token_status_label.setWordWrap(True)
        box.addWidget(self.token_status_label)

        token_row = QHBoxLayout()
        self.token_edit = QLineEdit()
        self.token_edit.setReadOnly(True)
        self.token_edit.setEchoMode(ECHO_PASSWORD)
        self.token_edit.setStyleSheet("font-family: monospace;")
        self.token_edit.setToolTip(
            "The shared secret the MCP server presents on every command. Read from\n"
            "the token file below; QGIS_MCP_TOKEN overrides it when set."
        )
        token_row.addWidget(self.token_edit, 1)

        self.token_show_btn = QPushButton("Show")
        self.token_show_btn.setFixedWidth(64)
        self.token_show_btn.clicked.connect(self._on_toggle_token_visibility)
        token_row.addWidget(self.token_show_btn)

        self.token_copy_btn = QPushButton("Copy")
        self.token_copy_btn.setFixedWidth(64)
        self.token_copy_btn.clicked.connect(self._on_copy_token)
        token_row.addWidget(self.token_copy_btn)
        box.addLayout(token_row)

        self.token_path_label = QLabel()
        self.token_path_label.setWordWrap(True)
        self.token_path_label.setTextInteractionFlags(TEXT_SELECTABLE_BY_MOUSE)
        self.token_path_label.setStyleSheet("color: palette(mid);")
        box.addWidget(self.token_path_label)

        button_row = QHBoxLayout()
        self.token_generate_btn = QPushButton("Generate new token")
        self.token_generate_btn.clicked.connect(self._on_generate_token)
        button_row.addWidget(self.token_generate_btn)
        self.token_revoke_btn = QPushButton("Revoke (disable auth)")
        self.token_revoke_btn.clicked.connect(self._on_revoke_token)
        button_row.addWidget(self.token_revoke_btn)
        button_row.addStretch()
        box.addLayout(button_row)

        return group

    def _refresh_token_state(self):
        """Repaint the token group from the store, which is the source of truth."""
        state = token_status()
        source = state["source"]
        token = read_token() or ""

        if source == "env":
            headline = "Active (environment variable QGIS_MCP_TOKEN)"
            detail = (
                "QGIS_MCP_TOKEN is set and takes precedence over the token file. "
                "Unset it where QGIS is launched to manage the token here."
            )
        elif source == "file":
            headline = "Active (token file)"
            detail = "Every command must present this token; both halves read it."
        else:
            headline = "Disabled - commands are accepted without a token"
            detail = "Generate a token to require one from every client."

        self.token_status_label.setText(f"Status: {headline}\n{detail}")
        self.token_status_label.setStyleSheet("")
        self.token_edit.setText(token)
        self.token_path_label.setText(f"Token file: {state['path'] or token_path()}")

        has_token = bool(token)
        from_env = source == "env"
        self.token_show_btn.setEnabled(has_token)
        self.token_copy_btn.setEnabled(has_token)
        self.token_revoke_btn.setEnabled(source == "file")
        self.token_generate_btn.setEnabled(not from_env)
        locked_hint = (
            "QGIS_MCP_TOKEN is set, so the token file is ignored. Unset it to manage the token here."
            if from_env
            else ""
        )
        self.token_generate_btn.setToolTip(locked_hint)
        self.token_revoke_btn.setToolTip(locked_hint)

        # A repaint must not leave the previous value on screen in the clear.
        self.token_edit.setEchoMode(ECHO_PASSWORD)
        self.token_show_btn.setText("Show")

    def _confirm_token_action(self, title, text, accept_label):
        """Ask before a token mutation; True when the user picked ``accept_label``."""
        box = QMessageBox(self)
        box.setIcon(MSGBOX_QUESTION)
        box.setWindowTitle(title)
        box.setText(text)
        accept = box.addButton(accept_label, MSGBOX_ACCEPT_ROLE)
        box.addButton("Cancel", MSGBOX_REJECT_ROLE)
        box.exec()
        return box.clickedButton() is accept

    def _token_write_failed(self, action, exc):
        """Report a failed token mutation in the dialog instead of aborting QGIS.

        `write_token`/`revoke_token` touch the filesystem: a read-only roaming
        profile, a full disk or (on Windows) an antivirus holding the file make
        them raise. An exception escaping a Qt slot calls qFatal, so the user
        would lose the whole session instead of reading "could not save".
        """
        QgsMessageLog.logMessage(f"Could not {action} the token: {exc}", LOG_TAG, MSG_CRITICAL)
        self.token_status_label.setText(f"Status: Could not {action} the token: {exc}")
        self.token_status_label.setStyleSheet("color: red;")

    def _on_generate_token(self):
        if self._confirm_token_action(
            "Generate a new token?",
            "This replaces the current token, and the new one takes effect on the "
            "next command. Clients that were configured with the old token stop "
            "working.",
            "Generate",
        ):
            try:
                write_token(generate_token())
            except Exception as exc:
                self._token_write_failed("save", exc)
                return
            self._refresh_token_state()

    def _on_revoke_token(self):
        if self._confirm_token_action(
            "Revoke the token?",
            "This deletes the token file and disables authentication: any process "
            "that can reach the socket port will be able to run commands in QGIS.",
            "Revoke",
        ):
            try:
                revoke_token()
            except Exception as exc:
                self._token_write_failed("remove", exc)
                return
            self._refresh_token_state()

    def _restore_label_later(self, button, text):
        """Put `text` back on `button` after 1.5s.

        The timer is parented to the dialog, so closing the dialog destroys it
        instead of letting it fire on a deleted widget.
        """
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: button.setText(text))
        timer.start(1500)

    def _on_copy_token(self):
        QgsApplication.clipboard().setText(read_token() or "")
        self.token_copy_btn.setText("Copied!")
        self._restore_label_later(self.token_copy_btn, "Copy")

    def _on_toggle_token_visibility(self):
        if self.token_edit.echoMode() == ECHO_PASSWORD:
            self.token_edit.setEchoMode(ECHO_NORMAL)
            self.token_show_btn.setText("Hide")
        else:
            self.token_edit.setEchoMode(ECHO_PASSWORD)
            self.token_show_btn.setText("Show")

    def _is_dev_install(self):
        """True when the plugin is running from a git-cloned repository."""
        return _is_dev_checkout(self.repo_dir)

    def _save_autostart(self, checked):
        """Persist the auto-start preference, and start the server if it is off.

        On a fresh install the server has never been started, so ticking this
        and getting nothing until the next QGIS launch reads as a broken
        checkbox. Unticking only affects the next launch - it does not stop a
        running server, which would be a surprising way to lose a live session.
        """
        QgsSettings().setValue(f"{SETTINGS_PREFIX}/autostart", checked)
        if checked and self.server is None and self.start_server:
            self.server = self.start_server()
            self.refresh_status()

    def _find_uv(self):
        """Return uv executable path, checking common Windows install locations."""
        uv = shutil.which("uv")
        if uv:
            return uv
        if sys.platform == "win32":
            localappdata = Path(os.environ.get("LOCALAPPDATA", ""))
            userprofile = Path(os.environ.get("USERPROFILE", ""))
            candidates = [
                localappdata / "Microsoft" / "WinGet" / "Links" / "uv.exe",
                userprofile / ".local" / "bin" / "uv.exe",
                userprofile / ".cargo" / "bin" / "uv.exe",
            ]
            for p in candidates:
                if p.exists():
                    return str(p)
        return None

    def _on_client_changed(self):
        self.refresh_status()

    def _copy_preview(self):
        QgsApplication.clipboard().setText(self.preview_edit.toPlainText())
        self.copy_btn.setText("Copied!")
        self._restore_label_later(self.copy_btn, "Copy")

    def _version_fix_commands(self, drifted):
        """The update commands for the drifted MCP servers, one per install kind.

        Only the MCP server side knows whether it was launched by uvx or from a
        source checkout, and the two commands are not interchangeable, so the
        plugin builds one per kind it was told about. Kept as a list rather than
        joined into a single line: `;` chains commands in bash and PowerShell
        but not in cmd.exe, and a copy button that silently produces a broken
        command line is worse than two lines to paste.
        """
        fixes = getattr(self.server, "client_fixes", None) or {}
        return sorted({fixes[v] for v in drifted if v in fixes}) or [DEFAULT_VERSION_FIX]

    def _copy_version_fix(self):
        QgsApplication.clipboard().setText(self.version_fix_btn.property("command"))
        self.version_fix_btn.setText("Copied!")
        self._restore_label_later(self.version_fix_btn, "Copy fix")

    def _get_client_info(self, client_name):
        return _client_config_registry(self.repo_dir).get(client_name)

    def _get_server_entry(self, client, remote, refresh=False):
        if remote:
            args = ["--from", self.github_url, "luiccian-qgis-mcp"]
            if refresh:
                args = ["--refresh-package", "luiccian-qgis-mcp", *args]
            entry = {
                "command": "uvx",
                "args": args,
            }
        else:
            uv = self._find_uv()
            if uv:
                entry = {
                    "command": uv,
                    "args": [
                        "--directory",
                        str(self.repo_dir),
                        "run",
                        "--no-sync",
                        "src/qgis_mcp/server.py",
                    ],
                }
            else:
                if sys.platform == "win32":
                    python = self.repo_dir / ".venv" / "Scripts" / "python.exe"
                else:
                    python = self.repo_dir / ".venv" / "bin" / "python"
                entry = {
                    "command": str(python),
                    "args": [str(self.repo_dir / "src" / "qgis_mcp" / "server.py")],
                }

        return entry

    def update_preview(self):
        client = self.client_combo.currentText()
        remote = self.mode_combo.currentText().startswith("Remote")
        refresh = remote and self.refresh_check.isChecked()
        # Refresh only applies to remote (uvx) mode.
        self.refresh_check.setEnabled(remote)
        info = self._get_client_info(client)

        if info.get("entry_format") == "manual":
            self.preview_label.setText("Copy this JSON into your MCP client config file:")
            entry = self._get_server_entry(client, remote, refresh)
            self.preview_edit.setPlainText(json.dumps({"mcpServers": {"qgis": entry}}, indent=2))
            return

        if info.get("entry_format") == "claude_cli":
            cli = info.get("cli", "claude")
            # QGIS is a global tool, so Claude Code installs it at user scope.
            scope = " -s user"
            if remote:
                refresh_flag = "--refresh-package luiccian-qgis-mcp " if refresh else ""
                target = f'uvx {refresh_flag}--from "{self.github_url}" luiccian-qgis-mcp'
            else:
                uv = self._find_uv() or "uv"
                target = (
                    f'"{uv}" --directory "{self.repo_dir}" run --no-sync src/qgis_mcp/server.py'
                )
            cmd = f"{cli} mcp add{scope} qgis -- {target}"
            self.preview_label.setText("Run this command in your terminal:")
            self.preview_edit.setPlainText(cmd)
            return

        self.preview_label.setText("Add to your client config file:")
        entry = self._get_server_entry(client, remote, refresh)
        self.preview_edit.setPlainText(json.dumps({"qgis": entry}, indent=2))

    def _refresh_versions(self):
        """Show this plugin's version against the MCP servers that connected.

        Set before every early return in refresh_status(): it does not depend on
        which client is selected, and it is the one place a user can see drift
        without asking an agent to run 'diagnose'.
        """
        mine = plugin_version()
        seen = sorted(getattr(self.server, "client_versions", ()) or ())
        if not seen:
            self.version_fix_btn.setVisible(False)
            self.version_label.setText(
                f"Plugin {mine}, MCP server: none connected yet "
                "(start the server and run a tool once)."
            )
            self.version_label.setStyleSheet("color: gray;")
            return
        drifted = [v for v in seen if v != mine]
        self.version_fix_btn.setVisible(bool(drifted))
        if drifted:
            fixes = self._version_fix_commands(drifted)
            self.version_fix_btn.setProperty("command", "\n".join(fixes))
            self.version_fix_btn.setToolTip("Copy to the clipboard:\n" + "\n".join(fixes))
            spelled = " and ".join(f"`{f}`" for f in fixes)
            self.version_label.setText(
                f"Plugin {mine}, MCP server {', '.join(seen)}. The versions differ. "
                "Everything still works, but tools added since the older half was built "
                f"will be missing. To match them, run {spelled}, then restart your MCP client."
            )
            self.version_label.setStyleSheet("color: orange;")
        else:
            self.version_label.setText(
                f"Plugin {mine}, MCP server {', '.join(seen)}. The versions match."
            )
            self.version_label.setStyleSheet("color: green;")

    def _refresh_server_state(self):
        """Show whether the socket server is listening."""
        if self.server is not None:
            self.server_label.setText(f"Server: running on port {self.server.port}")
            self.server_label.setStyleSheet("color: green;")
        else:
            self.server_label.setText("Server: not running")
            self.server_label.setStyleSheet("color: gray;")

    def refresh_status(self):
        self._refresh_server_state()
        self._refresh_versions()
        client = self.client_combo.currentText()
        info = self._get_client_info(client)

        if info.get("print_only"):
            self.status_label.setText(info.get("hint", "Run the command above in your terminal."))
            self.status_label.setStyleSheet("color: gray;")
            self.apply_btn.setEnabled(False)
            self.update_preview()
            return

        self.apply_btn.setEnabled(True)

        path = info["path"]
        key = info["key"]

        if path.exists():
            try:
                data = read_jsonc(path)
                if has_qgis_entry(data, key):
                    self.status_label.setText(f"Status: Configured in {path.name}")
                    self.status_label.setStyleSheet("color: green;")
                else:
                    self.status_label.setText(f"Status: Not configured in {path.name}")
                    self.status_label.setStyleSheet("color: orange;")
            except Exception as e:
                self.status_label.setText(f"Status: Error reading config: {e}")
                self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setText(f"Status: Config file not found ({path.name})")
            self.status_label.setStyleSheet("color: gray;")

        self.update_preview()

    def run_config(self):
        client = self.client_combo.currentText()
        remote = self.mode_combo.currentText().startswith("Remote")
        refresh = remote and self.refresh_check.isChecked()
        info = self._get_client_info(client)

        if info.get("print_only"):
            return

        path = info["path"]
        key = info["key"]
        entry = self._get_server_entry(client, remote, refresh)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = read_jsonc(path)
            if path.exists():
                backup_config(path)
            merge_qgis_entry(data, key, entry)
            write_json_atomic(path, data)

            self.refresh_status()
            QgsMessageLog.logMessage(f"Configured {client} at {path}", LOG_TAG, MSG_INFO)
        except Exception as e:
            QgsMessageLog.logMessage(f"Failed to configure {client}: {e}", LOG_TAG, MSG_CRITICAL)
            self.status_label.setText(f"Status: Failed to write: {e}")
            self.status_label.setStyleSheet("color: red;")
