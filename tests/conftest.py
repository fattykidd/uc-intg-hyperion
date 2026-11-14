"""
Test setup.

- Puts intg-hyperion/ on the import path (the folder name has a hyphen, so it is not a package).
- Runs ``async def`` tests in their own event loop, so no extra pytest plugin is needed.
"""

import asyncio
import inspect
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "intg-hyperion"))
sys.path.insert(0, str(TESTS_DIR))


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """Run ``async def`` tests with asyncio.run()."""
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None

    arguments = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
    asyncio.run(pyfuncitem.obj(**arguments))
    return True
