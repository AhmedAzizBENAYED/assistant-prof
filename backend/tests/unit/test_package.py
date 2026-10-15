import importlib
import re

import pytest

import assistant_prof

# Packages from ARCHITECTURE §5; each must stay importable on its own.
PACKAGES = [
    "core",
    "docmodel",
    "operations",
    "executor",
    "templates",
    "llm",
    "agent",
    "voice",
    "versions",
    "persistence",
    "api",
]


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", assistant_prof.__version__)


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name: str) -> None:
    module = importlib.import_module(f"assistant_prof.{name}")
    assert module.__doc__
