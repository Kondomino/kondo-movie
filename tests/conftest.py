"""
Global test setup:

1. Make `src/` importable for all test modules. The source layout is
   `src/movie_maker/...` but the project has no top-level package and pytest
   does not add `src/` automatically.

2. Set safe dummy values for the env vars that `src/config/config.py`
   interpolates at import time (DB_*, RENDER_*). Without these, importing
   anything that transitively pulls `config.config` (eg. `logger`,
   `gcp.db`, most `*_manager` modules) fails with
   `ValueError: Variable 'DB_HOST' not found`.

   These dummies must NEVER reach a real connection. Tests that exercise
   real DB/storage paths should override via monkeypatch or skip.
"""

import os
import sys
from pathlib import Path

# --- src on sys.path ---
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# --- safe dummy env defaults for config interpolation ---
_TEST_ENV_DEFAULTS = {
    # PostgreSQL.DEV
    "DB_HOST": "test-db-host",
    "DB_PORT": "5432",
    "DB_NAME": "test_db",
    "DB_USER": "test_user",
    "DB_PASSWORD": "test_password",
    # PostgreSQL.PROD (Render-named — legacy from Editora)
    "RENDER_INTERNAL_URL": "postgresql://test:test@test:5432/test",
    "RENDER_HOSTNAME": "test-host",
    "RENDER_DB_PORT": "5432",
    "RENDER_DB": "test_db",
    "RENDER_USR": "test_user",
    "RENDER_PWD": "test_password",
}
for _k, _v in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_k, _v)
