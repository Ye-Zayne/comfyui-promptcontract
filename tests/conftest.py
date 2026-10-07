import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture(scope="session")
def package():
    directory = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "promptcontract_test_package", directory / "__init__.py",
        submodule_search_locations=[str(directory)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def core(package):
    return sys.modules[package.__name__ + ".core"]
