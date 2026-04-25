"""
Smoke tests for the YAML admin list removal:

- `Authentication.ADMINS` is gone from config (no Pydantic attribute).
- `is_admin` is fail-closed: returns False for any input.
"""

import pytest


def test_admins_attr_removed_from_config():
    from config.config import settings

    assert not hasattr(settings.Authentication, "ADMINS"), (
        "settings.Authentication.ADMINS should not exist anymore — "
        "admin status moved to kondos-api"
    )


@pytest.mark.parametrize(
    "email",
    [
        "contato@kondomino.com.br",
        "victor@example.com",
        "anyone@anywhere.dev",
        "",
        None,
    ],
)
def test_is_admin_always_false(email):
    from utils.admin_utils import is_admin

    assert is_admin(email) is False
