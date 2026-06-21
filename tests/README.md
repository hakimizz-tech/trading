# Testing Notes

Use fast, deterministic tests by default. External providers, broker APIs, and
network calls should be tested with fixtures or mocks in `tests/`; live checks
belong in scripts such as `scripts/check_news_providers.py`.

Recommended local commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tests.test_news_providers tests.test_check_news_providers_script
```

Guidelines for future tests:

- Keep provider tests offline by normalizing fixture payloads.
- Use `unittest.mock.patch` for fetch functions and optional dependencies.
- Add one narrow test for each public helper or CLI behavior.
- Cover failure paths, empty results, and partial provider failures.
- Keep live smoke checks outside the unit suite.
