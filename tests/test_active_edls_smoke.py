"""
Smoke test: the 3 EDL families locked for v1 (city_beat, dream_pop, sonoma)
parse cleanly via the Pydantic `EDL` model.

Deliberately bypasses `EDLManager.load_edl_from_file` because that module
also imports `gcp.db` -> `logger` -> `config.config` which fails at import
time without a populated env (DB_HOST, etc). For a smoke test that only
needs to validate JSON shape, going directly through the Pydantic model
keeps the test hermetic and fast — no env, no DB, no config interpolation.

Run with:
    poetry run pytest tests/test_active_edls_smoke.py -v
"""

from pathlib import Path

import pytest

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
    return EDL.model_validate_json(json_data=path.read_text(encoding="utf-8"))


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
