"""
Pin the disk-based EDL loader. The engine is stateless — templates ship
with the image at `library/templates/{with_title|no_title}/`, and
`EDLManager.load_edl` reads them directly. This test ensures lookups
work for the three EDLs we ship in v1 (sonoma, city_beat, dream_pop)
including the orientation-suffix fallback (city_beat_landscape.json).
"""

from movie_maker.edl_manager import EDLManager


def test_load_sonoma_no_orientation_suffix():
    edl = EDLManager.load_edl(edl_id="sonoma", with_title=False)
    assert edl is not None
    # name field on EDL.model echoes the loaded id, sometimes lowercased
    assert edl.name.lower().startswith("sonoma")


def test_load_city_beat_landscape_via_orientation_fallback():
    # `city_beat.json` doesn't exist; loader should fall back to
    # `city_beat_landscape.json`.
    edl = EDLManager.load_edl(edl_id="city_beat", with_title=False, orientation="landscape")
    assert edl is not None
    assert "city beat" in edl.name.lower()
    assert "landscape" in edl.name.lower()


def test_load_city_beat_portrait_orientation():
    edl = EDLManager.load_edl(edl_id="city_beat", with_title=False, orientation="portrait")
    assert edl is not None
    assert "portrait" in edl.name.lower()


def test_load_dream_pop_landscape():
    edl = EDLManager.load_edl(edl_id="dream_pop", with_title=False, orientation="landscape")
    assert edl is not None
    assert "dream pop" in edl.name.lower()


def test_load_unknown_edl_returns_none():
    edl = EDLManager.load_edl(edl_id="this-edl-does-not-exist", with_title=False)
    assert edl is None


def test_load_with_title_variant():
    # sonoma exists in both with_title and no_title. with_title=True must
    # resolve to the with_title/ subfolder.
    edl = EDLManager.load_edl(edl_id="sonoma", with_title=True)
    assert edl is not None


def test_resolve_template_file_prefers_bare_id():
    # sonoma.json exists; should NOT fall through to a sonoma_landscape.json
    # which doesn't even exist. Pin the lookup precedence.
    path = EDLManager._resolve_template_file(
        edl_id="sonoma", with_title=False, orientation="landscape"
    )
    assert path is not None
    assert path.name == "sonoma.json"
