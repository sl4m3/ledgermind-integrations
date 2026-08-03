# Baseline test results

## Repository

- Repository: `ledgermind-integrations`
- Branch: `refactor/protocol-and-hermes-runtime`
- Baseline commit: `80997fb`
- Baseline tag: `pre-rust-core-boundary`
- Python: `3.11.15`

## Commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
PYTHONPATH="$PWD/src" \
/tmp/ledgermind-venv/bin/python -m pytest -q --tb=short

/tmp/ledgermind-venv/bin/python -m build
```

## Results

- Pytest: **10 passed**.
- Build: **passed**; sdist and wheel produced for `ledgermind-integrations==0.1.0`.
- Known warning: the sdist has no README file, so `build` reports a packaging warning; the build itself succeeds.

## Known skipped checks

- Rust checks are not applicable to the Python Integrations repository.
- `cargo deny` is not applicable until the Rust workspace is created in Stage 8.
- Ruff and mypy were not part of the Stage 0 baseline command set; they remain required for subsequent Python changes.
