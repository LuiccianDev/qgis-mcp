"""Build the QGIS plugin ZIP, with `qgis_listener/` as the archive root.

QGIS installs a plugin by unzipping it into the profile, so the archive has to
contain that one folder and nothing above it. The version comes from
`qgis_listener/metadata.txt`, which the release workflow already checks against
the tag, so a ZIP built by hand carries the same name as the one CI attaches.
"""

import configparser
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "qgis_listener"
EXCLUDE_PARTS = {"__pycache__", ".git"}
EXCLUDE_SUFFIXES = {".pyc"}
EXCLUDE_NAMES = {"AGENTS.md"}


def plugin_version() -> str:
    cfg = configparser.ConfigParser()
    cfg.read(PLUGIN / "metadata.txt", encoding="utf-8")
    return cfg["general"]["version"]


def build(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    version = plugin_version()
    archive = dest_dir / f"qgis_listener_v{version.replace('.', '-')}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PLUGIN.rglob("*")):
            if not path.is_file():
                continue
            if any(part in EXCLUDE_PARTS for part in path.parts):
                continue
            if path.suffix in EXCLUDE_SUFFIXES or path.name in EXCLUDE_NAMES:
                continue
            zf.write(path, path.relative_to(REPO).as_posix())
    return archive


if __name__ == "__main__":
    print(build(REPO / "dist"))
