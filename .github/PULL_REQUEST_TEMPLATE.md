## What & why
<!-- What does this change and what problem does it solve? -->

## How it was verified
<!-- Commands run + results. -->
- [ ] `ruff` + `mypy` + `pytest` pass (backend)
- [ ] `tsc` + `next build` pass (frontend, if touched)
- [ ] New behavior has tests; bug fixes have a regression test
- [ ] Schema change? Alembic migration added + `alembic check` clean
- [ ] Privileged/permission or tenancy-relevant paths have negative tests
- [ ] Docs updated if behavior/architecture changed

## Notes for reviewers
<!-- Anything to flag: trade-offs, follow-ups, risks. -->
