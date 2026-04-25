"""
Smoke test: the 3 EDL families locked for v1 (city_beat, dream_pop, sonoma)
parse cleanly via EDLManager.load_edl_from_file.

Lightweight by design — runs from JSON files on disk, no Firestore I/O,
no network. Run with:
    pytest tests/test_active_edls_smoke.py -v
"""

from pathlib import Path

import pytest

from movie_maker.edl_manager import EDLManager
from movie_maker.edl_model import EDL


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPO_ROOT / "library" / "templates"

# v1 active set — see references/kondo/architecture/video-tool-plan.html
ACTIVE_EDLS_WITH_TITLE = [
    "city_beat_landscape",
    "city_beat_portrait",
    "dream_pop_landscape",
    "dream_pop_portrait",
    "sonoma",
]
ACTIVE_EDLS_NO_TITLE = [
    "city_beat_landscape",
    "city_beat_portrait",
    "dream_pop_landscape",
    "dream_pop_portrait",
    "sonoma",
]


@pytest.mark.parametrize("edl_name", ACTIVE_EDLS_WITH_TITLE)
def test_with_title_edl_parses(edl_name: str) -> None:
    path = TEMPLATES_ROOT / "with_title" / f"{edl_name}.json"
    assert path.exists(), f"missing EDL JSON: {path}"

    edl = EDLManager.load_edl_from_file(edl_file_path=path)

    assert isinstance(edl, EDL), f"{edl_name}: not an EDL instance"
    assert edl.name, f"{edl_name}: missing name"
    assert edl.fps > 0, f"{edl_name}: invalid fps {edl.fps}"
    assert edl.clips, f"{edl_name}: empty clips"


@pytest.mark.parametrize("edl_name", ACTIVE_EDLS_NO_TITLE)
def test_no_title_edl_parses(edl_name: str) -> None:
    path = TEMPLATES_ROOT / "no_title" / f"{edl_name}.json"
    assert path.exists(), f"missing EDL JSON: {path}"

    edl = EDLManager.load_edl_from_file(edl_file_path=path)

    assert isinstance(edl, EDL), f"{edl_name}: not an EDL instance"
    assert edl.clips, f"{edl_name}: empty clips"
