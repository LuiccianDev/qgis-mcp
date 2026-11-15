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
- If `master` requires status checks on PRs, configure a repository secret `RELEASE_PR_TOKEN` (PAT or GitHub App token) so PRs opened by `Bump Release PR` automatically trigger `on: pull_request` workflows (GitHub's default `GITHUB_TOKEN` suppresses downstream workflow triggers).

1. Trigger **Actions → Bump Release PR → Run workflow** (`patch`, `minor`, `major`, or an explicit SemVer).
2. Review and squash-merge the generated `chore(release): vX.Y.Z` PR.
3. Tag `master` and push the tag:
   ```bash
   git checkout master && git pull
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
4. `.github/workflows/release.yml` isolates three jobs: `build` (read-only verification, ZIP + wheel/sdist build, checksums), `github-release` (SLSA build provenance attestations + GitHub Release), and `publish-pypi` (`uv publish` via OIDC Trusted Publishing in the `pypi` environment).
5. To enable automatic PyPI publishing:
   - On PyPI (`pypi.org/manage/account/publishing/`), add a **Trusted Publisher** for owner `LuiccianDev`, repository `qgis-mcp`, workflow `release.yml`, and environment `pypi` (project `luiccian-qgis-mcp`).
   - In GitHub (**Settings → Environments**), create the `pypi` environment.
   - In GitHub (**Settings → Secrets and variables → Actions → Variables**), set `PYPI_PUBLISH_ENABLED=true`.
