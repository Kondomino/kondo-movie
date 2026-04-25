"""
Smoke tests for the Stytch purge:

- `account.authentication` imports cleanly (no stytch_manager dependency)
- `authenticate` raises 501 — kondo-movie no longer authenticates
- `AccountActionsHandler.check_user` raises 501 — user lookups now via kondos-api
- The `stytch_manager` module is gone
- The `stytch` package is no longer installed
"""

import asyncio
import importlib

import pytest
from fastapi import HTTPException


def test_authentication_module_imports_without_stytch():
    """Module loads without pulling in stytch."""
    import account.authentication as mod

    assert hasattr(mod, "authenticate")
    # Old shim kept for callers; should resolve.
    assert hasattr(mod, "get_auth_dependency")


def test_stytch_manager_module_is_gone():
    """The stytch_manager module no longer exists in the codebase."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("account.stytch_manager")


def test_stytch_not_in_lockfile():
    """The stytch dependency is removed from poetry.lock.

    Asserting against the lockfile (not the live venv) is more deterministic —
    a stale venv may still have stytch installed even after `poetry lock`,
    which is fixed by `poetry install --sync` rather than a code change.
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    lock = (repo_root / "poetry.lock").read_text()
    assert "\nname = \"stytch\"" not in lock, "stytch is still in poetry.lock"


def test_authenticate_raises_501():
    from account.authentication import authenticate

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(authenticate(credentials=None))
    assert excinfo.value.status_code == 501
    assert "kondos-api" in excinfo.value.detail


def test_check_user_raises_501():
    from account.account_actions import AccountActionsHandler
    from account.account_actions_model import CheckUserRequest

    with pytest.raises(HTTPException) as excinfo:
        AccountActionsHandler().check_user(CheckUserRequest(email="x@example.com"))
    assert excinfo.value.status_code == 501
    assert "kondos-api" in excinfo.value.detail
