## Summary

<!-- Describe what this PR changes and why. -->

## Type of Change

- [ ] `feat`: New feature
- [ ] `fix`: Bug fix
- [ ] `docs`: Documentation only
- [ ] `ci`: CI/CD or workflow change
- [ ] `refactor` / `test` / `chore`: Internal improvement

## Checklist

- [ ] PR title follows Conventional Commits (`feat: ...`, `fix: ...`, `ci: ...`, etc.)
- [ ] `uv run --no-sync ruff check qgis_listener/ src/ tests/ install.py scripts/` passes
- [ ] `uv run --no-sync ruff format --check qgis_listener/ src/ tests/ install.py scripts/` passes
- [ ] Unit tests pass (`uv run --no-sync pytest tests/ --ignore=tests/test_qgis_live.py --ignore=tests/test_stress.py --ignore=tests/test_tdd.py -q`)
- [ ] Documentation (`README.md`, `AGENTS.md`, `docs/`) updated if tools, env vars, or behavior changed
