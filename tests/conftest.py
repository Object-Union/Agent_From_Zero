"""Pytest configuration: register --run-slow flag and load .env."""

import os

import pytest
from dotenv import load_dotenv


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests (real API calls)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (real API calls)")
    # Load .env so tests can access DEEPSEEK_API_KEY
    project_root = os.path.dirname(os.path.dirname(__file__))
    load_dotenv(os.path.join(project_root, ".env"))


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return  # Run everything
    skip_slow = pytest.mark.skip(reason="need --run-slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
