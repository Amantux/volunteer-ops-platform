# Contributing

Thanks for your interest in improving the Volunteer Operations Platform.

## Development setup
```bash
# Backend (Python 3.12)
cd backend
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"

# Frontend
cd web && npm ci
```
Or run the whole stack with `docker compose up --build`.

## Before you open a pull request
Everything CI checks, you can run locally — please make sure it passes:

```bash
# Backend
cd backend
.venv/bin/ruff check app tests        # lint
.venv/bin/mypy app                    # types
.venv/bin/python -m pytest -q         # tests

# Frontend
cd web
npx tsc --noEmit && npm run build
```

## Conventions
- **Small, focused PRs.** One logical change per commit; keep refactors separate from behavior
  changes.
- **Tests with behavior.** New behavior ships with tests; a bug fix ships with a regression test.
  Security- and permission-relevant paths need explicit negative tests.
- **Migrations, not `create_all`.** Schema changes go through Alembic; run `alembic upgrade head`
  then `alembic check` to confirm no model drift.
- **Match the surrounding code.** Thin routers → services → models; never put business logic in
  the frontend; every privileged action emits an `AuditEvent`.
- Conventional, imperative commit subjects (e.g. `Add …`, `Fix …`).

## Reporting bugs / requesting features
Use the issue templates. For **security vulnerabilities, do not open a public issue** — see
[SECURITY.md](SECURITY.md).

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).
