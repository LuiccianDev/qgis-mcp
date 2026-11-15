# GitHub Repository Governance & Branch Rulesets

Enterprise repositories (e.g. Microsoft, VS Code, Astral) enforce branch and tag rules at the GitHub repository level so CI gates cannot be bypassed.

## Recommended `master` Branch Ruleset

Configure under **Settings → Rules → Rulesets → New branch ruleset** targeting `refs/heads/master`:

- **Restrict deletions** & **Block force pushes**
- **Require a pull request before merging**
  - Allowed merge methods: **Squash** only (keeps `master` linear and matches `Semantic PR Title` enforcement)
  - Dismiss stale pull request approvals when new commits are pushed
- **Require linear history**
- **Require status checks to pass before merging** (strict / require branches to be up to date):
  - `locked-ubuntu`
  - `locked-windows`
  - `unpinned-ubuntu`
  - `Semantic PR Title`
  - `Analyze (python)`
  - `Analyze (actions)`

## Recommended Tag Protection Ruleset

Configure a **Tag ruleset** targeting `refs/tags/v*`:

- **Restrict creations**, **Restrict updates**, and **Restrict deletions** to repository admins / release automation.

## Automated Releases & PyPI Trusted Publishing (OIDC)

- Enable **Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests** so `Bump Release PR` can open PRs.
- `Bump Release PR` (`.github/workflows/bump-release.yml`) creates branch `release/vX.Y.Z`, opens the PR, and automatically triggers `.github/workflows/tests.yml` via `workflow_call` (no `RELEASE_PR_TOKEN` PAT required).

1. Trigger **Actions → Bump Release PR → Run workflow** (`patch`, `minor`, `major`, or an explicit SemVer).
2. Review and squash-merge the generated `chore(release): vX.Y.Z` PR into `master`.
3. Tag `master` and push the tag:
   ```bash
   git checkout master && git pull
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
4. `.github/workflows/release.yml` runs four isolated jobs: `verify-tag` (checks `pyproject.toml`, `metadata.txt`, and `CHANGELOG.md`), `build` (lockfile check, lint, unit tests, `qgis_listener_v*.zip`, wheel/sdist, `SHA256SUMS.txt`), `github-release` (SLSA provenance + GitHub Release with extracted changelog notes), and `publish-pypi` (`pypa/gh-action-pypi-publish` via OIDC + PEP 740 attestations in the `pypi` environment).
5. To enable automatic PyPI publishing:
   - On PyPI (`pypi.org/manage/account/publishing/`), add a **Trusted Publisher** for owner `LuiccianDev`, repository `qgis-mcp`, workflow `release.yml`, and environment `pypi` (project `luiccian-qgis-mcp`).
   - To also allow manual recovery via `publish-pypi.yml`, add a second Trusted Publisher on `pypi.org` for workflow `publish-pypi.yml` with environment `pypi` (and on `test.pypi.org` for workflow `publish-pypi.yml` with environment `testpypi`).
   - In GitHub (**Settings → Environments**), create the `pypi` environment (and optionally `testpypi` for staging).
   - In GitHub (**Settings → Secrets and variables → Actions → Variables**), set `PYPI_PUBLISH_ENABLED=true`.
6. For manual recovery or **TestPyPI** verification on an existing tag, run **Actions → Publish to PyPI (manual recovery)** (`.github/workflows/publish-pypi.yml`) with `tag` and `target_env` (`pypi` or `testpypi`).
