"""
Root conftest.py — shared pytest configuration.

The `pythonpath = src` setting in pytest.ini adds `src/` to sys.path for all
tests, so individual test files do not need manual sys.path manipulation.
Individual test files retain their own sys.path calls for backwards compatibility
when run directly (e.g. `python tests/test_foo.py`), but pytest itself does not
rely on them.
"""
import pytest


def pytest_collection_modifyitems(config, items):
    """Skip integration and slow tests unless explicitly requested."""
    if not config.getoption("--run-integration", default=False):
        skip_integration = pytest.mark.skip(reason="requires live API (pass --run-integration to enable)")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require a live ArangoDB / GenAI API connection",
    )
