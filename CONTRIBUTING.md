# Contributing

Thanks for your interest in PLUS Agent.

## Before Opening A Change

- Keep API keys, local databases, uploaded data, generated outputs, and PLUS runtime binaries out of commits.
- Run the test suite before proposing a change.
- Keep changes focused. Separate documentation, workflow logic, UI, and packaging changes when possible.

## Local Checks

```powershell
python -m unittest discover -s tests -v
python -m compileall agent tests scripts
python scripts/check_release_readiness.py
```

## Pull Request Expectations

- Explain the user-facing change.
- Include tests for behavior changes.
- Update documentation when setup, workflow, or privacy behavior changes.
- Do not commit `.env`, `.db`, `workspaces/`, `outputs/`, preview caches, or PLUS runtime binaries.
