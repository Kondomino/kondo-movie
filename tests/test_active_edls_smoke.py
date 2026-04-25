"""
Smoke test: the 3 EDL families locked for v1 (city_beat, dream_pop, sonoma)
parse cleanly via `EDLManager.load_edl_from_file` — the production code path.

Pre-lazy-import refactor, this test had to bypass `EDLManager` and go through
the Pydantic model directly because importing `edl_manager` triggered a real
Firestore connection at module load time. After moving `from gcp.db import
db_client` inside the methods that need it, importing `EDLManager` no longer
forces a DB connection, and we can validate the actual production loader.
"""

from pathlib import Path

import pytest

from movie_maker.edl_manager import EDLManager
from movie_maker.edl_model import EDL


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPO_ROOT / "library" / "templates"

# v1 active set — see references/kondo/architecture/video-tool-plan.html
ACTIVE_EDLS = [
    "city_beat_landscape",
    "city_beat_portrait",
    "dream_pop_landscape",
    "dream_pop_portrait",
    "sonoma",
]


def _load(flavor: str, edl_name: str) -> EDL:
    path = TEMPLATES_ROOT / flavor / f"{edl_name}.json"
    assert path.exists(), f"missing EDL JSON: {path}"
    edl = EDLManager.load_edl_from_file(edl_file_path=path)
    assert edl is not None, f"{flavor}/{edl_name}: load_edl_from_file returned None"
    return edl


@pytest.mark.parametrize("edl_name", ACTIVE_EDLS)
def test_with_title_edl_parses(edl_name: str) -> None:
    edl = _load("with_title", edl_name)
    assert edl.name, f"{edl_name}: missing name"
    assert edl.fps > 0, f"{edl_name}: invalid fps {edl.fps}"
    assert edl.clips, f"{edl_name}: empty clips"


@pytest.mark.parametrize("edl_name", ACTIVE_EDLS)
def test_no_title_edl_parses(edl_name: str) -> None:
    edl = _load("no_title", edl_name)
    assert edl.name, f"{edl_name}: missing name"
    assert edl.fps > 0, f"{edl_name}: invalid fps {edl.fps}"
    assert edl.clips, f"{edl_name}: empty clips"


def test_load_edl_from_file_does_not_touch_db():
    """
    Production-path validation that the lazy import works as advertised:
    `load_edl_from_file` is pure file+Pydantic and must not transitively
    require `gcp.db.db_client`. If a future refactor pulls db_client back
    into module scope (or inadvertently into this method), this test will
    catch it because the dummy DB env vars set in conftest cannot
    actually serve a Firestore connection — the import would error before
    file loading starts.
    """
    sample = TEMPLATES_ROOT / "with_title" / "sonoma.json"
    edl = EDLManager.load_edl_from_file(edl_file_path=sample)
    assert isinstance(edl, EDL)
