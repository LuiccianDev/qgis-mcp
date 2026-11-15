"""Release automation: validate versions, bump files, build plugin ZIP, and tag releases."""

from __future__ import annotations

import argparse
import configparser
import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def normalize_version(raw: str) -> str:
    """Strip a leading 'v' or 'refs/tags/v' and validate X.Y.Z SemVer format."""
    cleaned = raw.strip()
    if cleaned.startswith("refs/tags/"):
        cleaned = cleaned[len("refs/tags/") :]
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    if not SEMVER_RE.match(cleaned):
        raise ValueError(f"Invalid semantic version {raw!r}; expected X.Y.Z or vX.Y.Z")
    return cleaned


def read_pyproject_version(repo_root: Path = REPO_ROOT) -> str:
    """Read project version from pyproject.toml."""
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def read_metadata_version(repo_root: Path = REPO_ROOT) -> str:
    """Read plugin version from qgis_listener/metadata.txt."""
    cfg = configparser.ConfigParser()
    cfg.read(repo_root / "qgis_listener" / "metadata.txt", encoding="utf-8")
    return cfg["general"]["version"]


def verify_repo_versions(
    repo_root: Path = REPO_ROOT, expect_tag: str | None = None
) -> dict[str, str]:
    """Verify pyproject.toml, metadata.txt, CHANGELOG.md, and optional tag agree."""
    py_ver = read_pyproject_version(repo_root)
    meta_ver = read_metadata_version(repo_root)

    if not SEMVER_RE.match(py_ver):
        raise ValueError(f"pyproject.toml version {py_ver!r} is not valid SemVer (X.Y.Z)")
    if not SEMVER_RE.match(meta_ver):
        raise ValueError(f"qgis_listener/metadata.txt version {meta_ver!r} is not valid SemVer")
    if py_ver != meta_ver:
        raise ValueError(f"Version mismatch: pyproject.toml={py_ver} != metadata.txt={meta_ver}")

    changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{py_ver}]" not in changelog:
        raise ValueError(f"CHANGELOG.md is missing an entry header for '## [{py_ver}]'")

    if expect_tag is not None:
        expected_ver = normalize_version(expect_tag)
        if expected_ver != py_ver:
            raise ValueError(
                f"Tag {expect_tag!r} resolves to {expected_ver}, but repo version is {py_ver}"
            )

    return {
        "version": py_ver,
        "pyproject_version": py_ver,
        "metadata_version": meta_ver,
        "tag": f"v{py_ver}",
    }


def _update_pyproject_version(path: Path, new_version: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^(version\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\2",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"Could not find project version line in {path}")
    path.write_text(updated, encoding="utf-8")


def _update_metadata_version(path: Path, new_version: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r"(?m)^(version\s*=)\s*[^\r\n]+",
        rf"\g<1>{new_version}",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"Could not find version= line in {path}")
    path.write_text(updated, encoding="utf-8")


def _ensure_changelog_heading(path: Path, new_version: str) -> None:
    text = path.read_text(encoding="utf-8")
    heading = f"## [{new_version}]"
    if heading in text:
        return
    entry = f"{heading} - {date.today().isoformat()}\n\n"
    match = re.search(r"^## \[\d", text, flags=re.MULTILINE) or re.search(
        r"^## \[", text, flags=re.MULTILINE
    )
    if match:
        updated = text[: match.start()] + entry + text[match.start() :]
    else:
        sep = "" if text.endswith("\n") else "\n"
        updated = f"{text}{sep}\n{entry}"
    path.write_text(updated, encoding="utf-8")


def set_repo_version(repo_root: Path, new_version: str) -> dict[str, str]:
    """Atomically synchronize version across pyproject.toml, metadata.txt, and CHANGELOG.md."""
    normalized = normalize_version(new_version)
    _update_pyproject_version(repo_root / "pyproject.toml", normalized)
    _update_metadata_version(repo_root / "qgis_listener" / "metadata.txt", normalized)
    _ensure_changelog_heading(repo_root / "CHANGELOG.md", normalized)
    return verify_repo_versions(repo_root)


def extract_changelog_section(repo_root: Path, version_or_tag: str) -> str:
    """Extract the CHANGELOG.md body for a version/tag, or return a fallback summary."""
    version = normalize_version(version_or_tag)
    changelog_path = repo_root / "CHANGELOG.md"
    if not changelog_path.is_file():
        return f"Release v{version}"
    text = changelog_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^## \[{re.escape(version)}\][^\r\n]*\r?\n", flags=re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return f"Release v{version}"
    rest = text[match.end() :]
    next_heading = re.search(r"^## \[", rest, flags=re.MULTILINE)
    body = (rest[: next_heading.start()] if next_heading else rest).strip()
    return body or f"Release v{version}"


def _create_git_tag(repo_root: Path, tag: str, dry_run: bool = False) -> None:
    cmd = ["git", "tag", "-a", tag, "-m", f"Release {tag}"]
    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")
        return
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    if status.stdout.strip():
        raise RuntimeError("Working tree is dirty; commit version changes before tagging.")
    subprocess.run(cmd, cwd=repo_root, check=True)
    print(f"Created annotated git tag {tag} (push with: git push origin {tag})")


def _build_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate, bump, build, and tag releases.")
    parser.add_argument(
        "--check", action="store_true", help="Verify repo versions & CHANGELOG sync"
    )
    parser.add_argument("--expect-tag", help="Verify version matches this tag (e.g. v0.1.0)")
    parser.add_argument("--set-version", help="Bump version across pyproject/metadata/CHANGELOG")
    parser.add_argument("--build", action="store_true", help="Build the plugin ZIP into dist/")
    parser.add_argument("--tag", action="store_true", help="Create annotated git tag v<version>")
    parser.add_argument(
        "--extract-notes",
        metavar="TAG_OR_VERSION",
        help="Extract CHANGELOG.md notes for the given version or tag",
    )
    parser.add_argument(
        "--output",
        help="Optional output file path for --extract-notes",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print git tag without creating it")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _build_args(argv)
    if not (
        args.check
        or args.set_version
        or args.build
        or args.tag
        or args.expect_tag
        or args.extract_notes
    ):
        args.check = True

    try:
        if args.extract_notes:
            notes = extract_changelog_section(REPO_ROOT, args.extract_notes)
            if args.output:
                Path(args.output).write_text(f"{notes}\n", encoding="utf-8")
            else:
                print(notes)
            return 0

        if args.set_version:
            info = set_repo_version(REPO_ROOT, args.set_version)
            print(f"Updated repository version to {info['version']} (tag {info['tag']})")
        else:
            info = verify_repo_versions(REPO_ROOT, expect_tag=args.expect_tag)
            print(f"Verified version {info['version']} (tag {info['tag']})")

        if args.build:
            if str(REPO_ROOT) not in sys.path:
                sys.path.insert(0, str(REPO_ROOT))
            from scripts.build_plugin_zip import build

            archive = build(REPO_ROOT / "dist")
            print(f"Built plugin ZIP: {archive}")

        if args.tag:
            _create_git_tag(REPO_ROOT, info["tag"], dry_run=args.dry_run)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
