#!/usr/bin/env python3
"""Multi-client installer for Luiccian QGIS MCP.

Symlinks or extracts the QGIS plugin and configures MCP clients (Antigravity,
Claude Desktop, Claude Code, or manual JSON output).

Usage:
    python install.py                          # Interactive menu
    python install.py --list-qgis              # Show detected QGIS installs/profiles
    python install.py --plugin-only            # Install/link plugin only + print JSON
    python install.py --plugin-only --from-zip # Build/extract ZIP plugin only
    python install.py --print-config           # Print manual MCP JSON config
    python install.py --non-interactive --clients antigravity,claude-desktop
    python install.py --remote                 # Use uvx (no local clone needed)
    python install.py --uninstall --clients antigravity
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

REPO_DIR = Path(__file__).resolve().parent
PLUGIN_SRC = REPO_DIR / "qgis_listener"
# Zip archive instead of git+ URL: uvx then needs no git executable, which is
# not visible to GUI-spawned MCP servers (e.g. Claude Desktop on Windows).
GITHUB_URL = "https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/master.zip"
GITHUB_RELEASE_API = "https://api.github.com/repos/LuiccianDev/qgis-mcp/releases/latest"

# ── Platform helpers ────────────────────────────────────────────────────────


def _home() -> Path:
    return Path.home()


def _appdata() -> Path:
    """Windows %APPDATA% or fallback."""
    return Path(os.environ.get("APPDATA", _home() / "AppData" / "Roaming"))


def _qgis_base_dir(version: str) -> Path:
    """Return the QGIS data root for a given major version ('3' or '4')."""
    folder = f"QGIS{version}"
    bases = {
        "linux": _home() / ".local" / "share" / "QGIS" / folder,
        "darwin": _home() / "Library" / "Application Support" / "QGIS" / folder,
        "win32": _appdata() / "QGIS" / folder,
    }
    base = bases.get(sys.platform)
    if base is None:
        sys.exit(f"Unsupported platform: {sys.platform}")
    return base


def _detect_qgis_version() -> str:
    """Return '4' if QGIS4 profile dir exists, else '3'."""
    if _qgis_base_dir("4").exists():
        return "4"
    return "3"


def qgis_plugins_dir(profile: str, version: str = "auto") -> Path:
    if version == "auto":
        version = _detect_qgis_version()
    return _qgis_base_dir(version) / "profiles" / profile / "python" / "plugins"


def detect_qgis_installations() -> list[dict[str, object]]:
    """Discover installed QGIS major versions, user profiles, and plugin status."""
    found: list[dict[str, object]] = []
    for ver in ("4", "3"):
        base = _qgis_base_dir(ver)
        profiles_dir = base / "profiles"
        if not profiles_dir.is_dir():
            continue
        profiles = sorted(p.name for p in profiles_dir.iterdir() if p.is_dir())
        installed = [
            name
            for name in profiles
            if (profiles_dir / name / "python" / "plugins" / "qgis_listener").exists()
            or (profiles_dir / name / "python" / "plugins" / "qgis_listener").is_symlink()
        ]
        found.append(
            {
                "version": ver,
                "base_dir": base,
                "profiles": profiles,
                "installed_profiles": installed,
            }
        )
    return found


def print_qgis_installations() -> None:
    """Print detected QGIS installations, profiles, and listener plugin status."""
    installations = detect_qgis_installations()
    if not installations:
        print("No QGIS profile directories detected.")
        return
    print("Detected QGIS installations:")
    for item in installations:
        ver = item["version"]
        base = item["base_dir"]
        profiles = item["profiles"]
        installed = set(item["installed_profiles"])
        print(f"  QGIS {ver}: {base}")
        if not profiles:
            print("    (no profiles directory entries)")
            continue
        for name in profiles:
            status = "installed" if name in installed else "not installed"
            print(f"    - profile '{name}' [{status}]")


# ── Client config paths ────────────────────────────────────────────────────

ClientInfo = dict[str, str | Path | bool]


def _client_registry() -> dict[str, ClientInfo]:
    """Return per-client metadata.  Paths resolved at call time."""
    home = _home()
    appdata = _appdata()

    if sys.platform == "darwin":
        claude_cfg = (
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        )
    elif sys.platform == "win32":
        claude_cfg = appdata / "Claude" / "claude_desktop_config.json"
    else:
        claude_cfg = home / ".config" / "Claude" / "claude_desktop_config.json"

    # Antigravity (Google Gemini / Antigravity)
    antigravity_cfg = (
        Path(os.environ.get("ANTIGRAVITY_CONFIG_DIR", home / ".gemini" / "antigravity"))
        / "mcp_config.json"
    )

    return {
        "antigravity": {"path": antigravity_cfg, "key": "mcpServers"},
        "claude-desktop": {"path": claude_cfg, "key": "mcpServers"},
        "claude-code": {"print_only": True, "cli": "claude"},
        "manual": {"print_only": True, "entry_format": "manual"},
    }


# ── MCP server entry builders ──────────────────────────────────────────────


def _venv_python() -> Path:
    """Return the Python executable inside the project venv."""
    if sys.platform == "win32":
        return REPO_DIR / ".venv" / "Scripts" / "python.exe"
    return REPO_DIR / ".venv" / "bin" / "python"


def _is_venv_ready() -> bool:
    """Check if the venv exists and qgis_mcp is importable."""
    python = _venv_python()
    if not python.exists():
        return False
    result = subprocess.run(
        [str(python), "-c", "import qgis_mcp"],
        capture_output=True,
    )
    return result.returncode == 0


def _find_uv() -> str | None:
    """Return uv executable path, checking common Windows install locations."""
    uv = shutil.which("uv")
    if uv:
        return uv
    if sys.platform == "win32":
        localappdata = Path(os.environ.get("LOCALAPPDATA", ""))
        userprofile = Path(os.environ.get("USERPROFILE", _home()))
        candidates = [
            localappdata / "Microsoft" / "WinGet" / "Links" / "uv.exe",
            userprofile / ".local" / "bin" / "uv.exe",
            userprofile / ".cargo" / "bin" / "uv.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return None


def setup_venv() -> None:
    """Create venv and install dependencies, using uv if available, else pip."""
    if _is_venv_ready():
        print("  Dependencies already installed.")
        return

    uv = _find_uv()
    if uv:
        print("  Setting up dependencies with uv...")
        subprocess.run([uv, "sync"], cwd=str(REPO_DIR), check=True)
    else:
        print("  uv not found, falling back to pip...")
        venv_dir = REPO_DIR / ".venv"
        if not venv_dir.exists():
            print("  Creating virtual environment...")
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        python = str(_venv_python())
        subprocess.run([python, "-m", "pip", "install", "-e", str(REPO_DIR)], check=True)

    print("  Dependencies installed.")


def _local_entry() -> dict:
    uv = _find_uv()
    if uv:
        # `--directory` is preferred over `cwd` because some MCP clients (notably
        # MSIX-packaged Claude Desktop on Windows) run servers in a sandbox that
        # silently ignores `cwd`. `--directory` bakes the project path into the
        # command itself so it works regardless of the spawn environment.
        return {
            "command": uv,
            "args": [
                "--directory",
                str(REPO_DIR),
                "run",
                "--no-sync",
                "src/qgis_mcp/server.py",
            ],
        }
    # Fallback: run directly from the venv Python
    return {
        "command": str(_venv_python()),
        "args": [str(REPO_DIR / "src" / "qgis_mcp" / "server.py")],
    }


def _remote_entry() -> dict:
    return {
        "command": "uvx",
        "args": ["--from", GITHUB_URL, "luiccian-qgis-mcp"],
    }


def format_manual_config(remote: bool = False) -> str:
    """Return a ready-to-paste MCP client JSON snippet for manual setup."""
    entry = _remote_entry() if remote else _local_entry()
    return json.dumps({"mcpServers": {"qgis": entry}}, indent=2)


# ── Plugin installation ────────────────────────────────────────────────────


def _remove_target(target: Path, force: bool = False) -> None:
    """Remove a plugin target - handles files, symlinks, Windows junctions, and dirs.

    Path.is_symlink() returns False for Windows directory junctions (created via
    `mklink /J`), so we also check os.path.islink() and fall back to rmdir() for
    junctions before resorting to shutil.rmtree() on real directories.

    A real directory is a Plugin Manager install, not something this script put
    there, so deleting it asks first unless `force` is set.
    """
    if target.is_symlink() or os.path.islink(target) or target.is_file():
        target.unlink()
        return
    if sys.platform == "win32":
        try:
            target.rmdir()  # cleanly removes a junction without touching the target
            return
        except OSError:
            pass
    if not force:
        answer = input(f"  {target} is a real directory, not a link. Delete it? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            sys.exit("Aborted: existing plugin directory left in place.")
    shutil.rmtree(target)


def install_plugin(profile: str, version: str = "auto", force: bool = False) -> Path:
    plugins_dir = qgis_plugins_dir(profile, version)
    target = plugins_dir / "qgis_listener"

    if target.is_symlink() or target.exists() or os.path.islink(target):
        if target.is_symlink() and target.resolve() == PLUGIN_SRC.resolve():
            print(f"  Plugin already linked: {target}")
            return target
        print(f"  Removing existing: {target}")
        _remove_target(target, force)

    plugins_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        # Symlinks may require admin on Windows; fall back to dir junction
        try:
            target.symlink_to(PLUGIN_SRC, target_is_directory=True)
        except OSError:
            # Junction via direct API call (no shell, unlike `mklink /J`)
            import _winapi

            _winapi.CreateJunction(str(PLUGIN_SRC), str(target))
    else:
        target.symlink_to(PLUGIN_SRC)

    print(f"  Linked: {target} -> {PLUGIN_SRC}")
    return target


def install_plugin_from_zip(
    zip_path: Path, profile: str, version: str = "auto", force: bool = False
) -> Path:
    """Extract a validated qgis_listener plugin ZIP into the QGIS plugins directory."""
    if not zip_path.is_file():
        sys.exit(f"Plugin ZIP not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if "qgis_listener/metadata.txt" not in names:
            sys.exit(
                f"Invalid plugin ZIP {zip_path}: missing 'qgis_listener/metadata.txt' at root."
            )
        for name in names:
            posix = PurePosixPath(name.replace("\\", "/"))
            if "\\" in name or posix.is_absolute() or ".." in posix.parts:
                sys.exit(f"Unsafe path in plugin ZIP {zip_path}: {name!r}")
            if posix.parts and posix.parts[0] != "qgis_listener":
                sys.exit(
                    f"Invalid plugin ZIP {zip_path}: unexpected top-level entry {posix.parts[0]!r}"
                )

        plugins_dir = qgis_plugins_dir(profile, version)
        target = plugins_dir / "qgis_listener"
        if target.is_symlink() or target.exists() or os.path.islink(target):
            print(f"  Removing existing: {target}")
            _remove_target(target, force)

        plugins_dir.mkdir(parents=True, exist_ok=True)
        zf.extractall(plugins_dir)

    print(f"  Installed from ZIP: {target}")
    return target


def download_release_zip(dest_dir: Path, api_url: str = GITHUB_RELEASE_API) -> Path:
    """Download the latest qgis_listener_v*.zip asset from GitHub Releases."""
    req = urllib.request.Request(
        api_url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "qgis-mcp"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            release = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Failed to fetch latest release from {api_url}: {exc}")

    asset = next(
        (
            a
            for a in release.get("assets", [])
            if isinstance(a, dict)
            and str(a.get("name", "")).startswith("qgis_listener_v")
            and str(a.get("name", "")).endswith(".zip")
            and a.get("browser_download_url")
        ),
        None,
    )
    if asset is None:
        sys.exit(f"No qgis_listener_v*.zip asset found in release from {api_url}.")

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / asset["name"]
    dl_req = urllib.request.Request(
        asset["browser_download_url"],
        headers={"User-Agent": "qgis-mcp"},
    )
    try:
        with urllib.request.urlopen(dl_req, timeout=60) as resp:
            out_path.write_bytes(resp.read())
    except (urllib.error.URLError, OSError) as exc:
        sys.exit(f"Failed to download {asset['browser_download_url']}: {exc}")

    return out_path


def uninstall_plugin(profile: str, version: str = "auto", force: bool = False) -> None:
    target = qgis_plugins_dir(profile, version) / "qgis_listener"
    if target.is_symlink() or target.exists() or os.path.islink(target):
        _remove_target(target, force)
        print(f"  Removed: {target}")
    else:
        print(f"  Not installed: {target}")


# ── Client configuration ───────────────────────────────────────────────────


def _jsonc_to_json(text: str) -> str:
    """Convert potential JSONC json file to valid JSON.

    One pass, with the string-literal branch first so anything quoted is kept
    verbatim: URLs (`https://`), a `//` or a `/*` inside a value. Block and line
    comments outside strings are dropped, then trailing commas in objects and
    arrays. `[^\\n]` in the line-comment branch because DOTALL is on for the
    block comment branch and `.` would otherwise swallow the rest of the file.
    """
    stripped = re.sub(
        r'("(?:\\.|[^"\\])*")|/\*.*?\*/|//[^\n]*',
        lambda m: m.group(1) or "",
        text,
        flags=re.DOTALL,
    )
    return re.sub(r",\s*([}\]])", r"\1", stripped)


def _read_json(path: Path) -> dict:
    if not path.exists() or not (text := path.read_text(encoding="utf-8").strip()):
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    try:
        cleaned = _jsonc_to_json(text)
        config = json.loads(cleaned)
        print(f"  Note: {path} has comments; they are not preserved when it is rewritten.")
        return config
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse {path}: not valid JSON or JSONC. Error: {e}") from e


def _backup(path: Path) -> None:
    """Copy a config aside under a timestamped `.bak-` suffix.

    Timestamped rather than a fixed `.bak`: a second run would otherwise
    overwrite the only untouched copy with the one the first run wrote.
    """
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    bak = path.with_suffix(f"{path.suffix}.bak-{stamp}")
    n = 0
    while bak.exists():  # two runs inside the same second
        n += 1
        bak = path.with_suffix(f"{path.suffix}.bak-{stamp}-{n}")
    shutil.copy2(path, bak)
    print(f"  Backup: {bak}")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize into a sibling temp file first: an open(path, "w") truncates the
    # existing config before json.dumps runs, so a failure there loses it.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def configure_client(client_name: str, remote: bool) -> None:
    registry = _client_registry()
    info = registry[client_name]

    # Manual configuration snippet - print JSON only, leave existing configs untouched
    if info.get("entry_format") == "manual":
        print()
        print("  Manual MCP client configuration (paste into your client's JSON config):")
        print()
        for line in format_manual_config(remote).splitlines():
            print(f"    {line}")
        print()
        return

    # CLI-based client (Claude Code): use its `mcp add` subcommand
    if info.get("print_only"):
        cli_name = info.get("cli", "claude")
        cli_bin = shutil.which(cli_name)
        if not cli_bin:
            print(f"  '{cli_name}' CLI not found in PATH – skipping.")
            return

        uv = _find_uv()
        if remote:
            add_args = ["uvx", "--from", GITHUB_URL, "luiccian-qgis-mcp"]
        elif uv:
            add_args = [
                uv,
                "--directory",
                str(REPO_DIR),
                "run",
                "--no-sync",
                "src/qgis_mcp/server.py",
            ]
        else:
            add_args = [
                str(_venv_python()),
                str(REPO_DIR / "src" / "qgis_mcp" / "server.py"),
            ]

        # Claude Code supports scoped installs; use user scope for QGIS (global tool)
        subprocess.run(
            [cli_bin, "mcp", "remove", "-s", "user", "qgis"],
            capture_output=True,
        )
        result = subprocess.run(
            [cli_bin, "mcp", "add", "-s", "user", "qgis", "--", *add_args],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  Configured Claude Code (user scope).")
        else:
            print(f"  Failed to configure Claude Code: {result.stderr.strip()}")
        return

    path = Path(info["path"])
    key = info["key"]
    entry = _remote_entry() if remote else _local_entry()

    config = _read_json(path)
    if path.exists():
        _backup(path)

    # Not setdefault: an existing key holding a list or a string would make the
    # assignment below raise instead of being replaced.
    if not isinstance(config.get(key), dict):
        config[key] = {}
    config[key]["qgis"] = entry
    _write_json(path, config)
    print(f"  Wrote: {path}")


def unconfigure_client(client_name: str) -> None:
    registry = _client_registry()
    info = registry[client_name]

    if info.get("entry_format") == "manual":
        print("  Manual: remove the 'qgis' entry from your MCP client's config file manually.")
        return

    if info.get("print_only"):
        cli_name = info.get("cli", "claude")
        cli_bin = shutil.which(cli_name)
        if not cli_bin:
            print(f"  '{cli_name}' CLI not found in PATH – skipping.")
            return

        result = subprocess.run(
            [cli_bin, "mcp", "remove", "-s", "user", "qgis"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  Removed qgis from Claude Code.")
        else:
            print(f"  Not configured in Claude Code: {result.stderr.strip()}")
        return

    path = Path(info["path"])
    key = info["key"]

    config = _read_json(path)
    if key in config and "qgis" in config[key]:
        _backup(path)
        del config[key]["qgis"]
        if not config[key]:
            del config[key]
        _write_json(path, config)
        print(f"  Removed qgis from: {path}")
    else:
        print(f"  Not configured: {path}")


# ── Interactive menu ────────────────────────────────────────────────────────

ALL_CLIENTS = [
    "antigravity",
    "claude-desktop",
    "claude-code",
    "manual",
]


def interactive_menu() -> list[str]:
    print("\nAvailable MCP clients:")
    tags = {
        "manual": " (print JSON snippet only)",
    }
    for i, name in enumerate(ALL_CLIENTS, 1):
        print(f"  {i}. {name}{tags.get(name, '')}")
    print("  a. All")
    print("  q. Skip client configuration")

    choice = input("\nSelect clients (comma-separated numbers, 'a', or 'q'): ").strip().lower()
    if choice == "q":
        return []
    if choice == "a":
        return list(ALL_CLIENTS)

    selected = []
    for part in choice.split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= len(ALL_CLIENTS):
            selected.append(ALL_CLIENTS[int(part) - 1])
    return selected


def interactive_mode_choice() -> bool:
    choice = input(
        "\nInstall mode:\n  1. Local dev (uv run from repo)\n  2. Remote (uvx from GitHub)\nChoice [1]: "
    ).strip()
    return choice == "2"


# ── Main ────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install the Luiccian QGIS Listener plugin and configure MCP clients.",
    )
    parser.add_argument("--profile", default="default", help="QGIS profile name (default: default)")
    parser.add_argument(
        "--qgis-version",
        default="auto",
        choices=["auto", "3", "4"],
        help="QGIS major version to target (default: auto-detect, prefers 4)",
    )
    parser.add_argument(
        "--clients", help="Comma-separated client names (e.g. antigravity,claude-desktop)"
    )
    parser.add_argument("--non-interactive", action="store_true", help="Skip interactive prompts")
    parser.add_argument(
        "--remote", action="store_true", help="Use uvx from GitHub instead of local uv run"
    )
    parser.add_argument(
        "--from-zip",
        nargs="?",
        const="auto",
        default=None,
        metavar="PATH",
        help="Install plugin from a ZIP archive (omit PATH to build dist/qgis_listener_v*.zip)",
    )
    parser.add_argument(
        "--list-qgis",
        action="store_true",
        help="List detected QGIS installations and profiles, then exit",
    )
    parser.add_argument(
        "--plugin-only",
        action="store_true",
        help="Install/link only the QGIS plugin and print manual MCP JSON without editing clients",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the manual MCP JSON config snippet (local or --remote) and exit",
    )
    parser.add_argument("--uninstall", action="store_true", help="Remove plugin and client configs")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete an existing real plugin directory without asking",
    )
    return parser.parse_args()


def _do_plugin(args: argparse.Namespace, qgis_ver: str, force: bool) -> None:
    if args.uninstall:
        print("[1/3] Removing QGIS plugin...")
        uninstall_plugin(args.profile, qgis_ver, force)
        return

    print("[1/3] Installing QGIS plugin...")
    from_zip = getattr(args, "from_zip", None)
    if from_zip is not None:
        if from_zip == "auto":
            from scripts.build_plugin_zip import build as build_plugin_zip

            zip_path = build_plugin_zip(REPO_DIR / "dist")
        else:
            zip_path = Path(from_zip)
        install_plugin_from_zip(zip_path, args.profile, qgis_ver, force)
    elif args.remote:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = download_release_zip(Path(tmpdir))
            install_plugin_from_zip(zip_path, args.profile, qgis_ver, force)
    else:
        install_plugin(args.profile, qgis_ver, force)


def _do_deps(args: argparse.Namespace) -> None:
    """Set up the venv, which an uninstall and remote (uvx) mode do not need."""
    if args.uninstall or args.remote:
        return
    print("\n[2/3] Setting up dependencies...")
    setup_venv()


def _do_clients(args: argparse.Namespace, clients: list[str]) -> None:
    if getattr(args, "plugin_only", False):
        if not args.uninstall:
            print("\n[3/3] Manual MCP client config (--plugin-only):")
            print(format_manual_config(args.remote))
        return

    # --clients is honoured with or without --non-interactive; only ask when it is absent.
    if not clients and not args.non_interactive:
        clients = interactive_menu()
    if not clients:
        return

    # --remote wins outright: prompting would let Enter flip it back to local after
    # the venv step was already skipped, leaving the config pointing at nothing.
    remote = args.remote or (
        interactive_mode_choice() if not args.uninstall and not args.non_interactive else False
    )

    print(f"\n[3/3] {'Removing' if args.uninstall else 'Configuring'} MCP clients...")
    for client in clients:
        print(f"\n  -- {client} --")
        try:
            if args.uninstall:
                unconfigure_client(client)
            else:
                configure_client(client, remote)
        except (ValueError, OSError) as exc:
            # One unreadable or malformed config must not cost the user every
            # other client they asked for.
            print(f"  Skipped {client}: {exc}")


def main() -> None:
    args = _parse_args()

    if args.list_qgis:
        print_qgis_installations()
        return

    if args.print_config:
        print(format_manual_config(args.remote))
        return

    # Validate before anything is touched, so a typo does not cost a symlink or a venv.
    clients = [c.strip() for c in args.clients.split(",")] if args.clients else []
    valid = set(_client_registry())
    invalid = [c for c in clients if c not in valid]
    if invalid:
        sys.exit(f"Unknown clients: {', '.join(invalid)}.  Valid: {', '.join(sorted(valid))}")

    force = args.force or args.non_interactive
    qgis_ver = args.qgis_version
    if qgis_ver == "auto":
        qgis_ver = _detect_qgis_version()

    print(f"Luiccian QGIS MCP Installer ({'uninstall' if args.uninstall else 'install'})")
    print(f"Platform:     {sys.platform}")
    print(f"Profile:      {args.profile}")
    print(f"QGIS version: {qgis_ver}")
    print()

    _do_plugin(args, qgis_ver, force)
    _do_deps(args)
    _do_clients(args, clients)

    print("\n" + "=" * 50)
    if args.uninstall:
        print("Uninstall complete.")
    else:
        print("Installation complete.")
        print("\nNext steps:")
        print("  1. Restart QGIS and enable the 'Luiccian QGIS Listener' plugin")
        print("  2. Click 'Start Server' in the MCP dock widget")
        print("  3. Restart your MCP client to pick up the new config")


if __name__ == "__main__":
    main()
