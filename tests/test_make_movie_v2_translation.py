"""
Pin the v2 → legacy translation that bridges the proxied-identity contract
from kondos-api to the engine's internal pipeline. These tests are pure
model-level — no Firestore, no storage, no MovieMaker.
"""

import pytest

from movie_maker.movie_actions_model import (
    MakeMovieAgent,
    MakeMovieKondo,
    MakeMovieCapabilities,
    MakeMovieRequestV2,
    v2_to_legacy_request,
)


def _v2(**overrides) -> MakeMovieRequestV2:
    base = dict(
        job_id="job-abc-123",
        agent=MakeMovieAgent(id=42, name="Maria Silva"),
        kondo=MakeMovieKondo(id=7001, address="Rua das Palmeiras, 123 — São Paulo"),
        media_urls=[
            "https://cdn.example.com/m1.jpg",
            "https://cdn.example.com/m2.jpg",
            "https://cdn.example.com/m3.jpg",
        ],
        description="Belo apartamento de 3 quartos com vista para o parque.",
        edl_id="city_beat",
        voice_id="lucas",
        music_url=None,
        webhook_url="https://api.kondomino.com.br/internal/video-webhook",
        capabilities=MakeMovieCapabilities(
            duration_max_seconds=60,
            images_max=12,
            captions_enabled=False,
        ),
    )
    base.update(overrides)
    return MakeMovieRequestV2(**base)


def test_translation_synthesizes_session_from_proxied_ids():
    legacy = v2_to_legacy_request(_v2())
    assert legacy.request_id.user.id == "42"
    assert legacy.request_id.project.id == "7001"
    assert legacy.request_id.version.id == "job-abc-123"


def test_translation_maps_media_to_ordered_images():
    v2 = _v2()
    legacy = v2_to_legacy_request(v2)
    assert legacy.ordered_images == v2.media_urls
    assert legacy.image_repos is None
    assert legacy.excluded_images is None


def test_translation_maps_edl_id_to_template_and_webhook():
    legacy = v2_to_legacy_request(_v2())
    assert legacy.template == "city_beat"
    assert legacy.webhook_url == "https://api.kondomino.com.br/internal/video-webhook"


def test_translation_builds_narration_from_description_and_voice():
    legacy = v2_to_legacy_request(_v2())
    narration = legacy.config.narration
    assert narration is not None
    assert narration.enabled is True
    assert narration.voice == "lucas"
    assert narration.script.startswith("Belo apartamento")
    assert narration.captions is False


def test_translation_respects_captions_flag():
    legacy = v2_to_legacy_request(
        _v2(capabilities=MakeMovieCapabilities(
            duration_max_seconds=60,
            images_max=12,
            captions_enabled=True,
        )),
    )
    assert legacy.config.narration.captions is True


def test_translation_voice_id_optional():
    legacy = v2_to_legacy_request(_v2(voice_id=None))
    assert legacy.config.narration.voice is None
    # script still mandatory and present
    assert legacy.config.narration.script.startswith("Belo apartamento")


def test_v2_rejects_empty_media_urls():
    with pytest.raises(Exception):
        _v2(media_urls=[])


def test_v2_rejects_blank_required_strings():
    with pytest.raises(Exception):
        _v2(job_id="")
    with pytest.raises(Exception):
        _v2(edl_id="   ")
    with pytest.raises(Exception):
        _v2(webhook_url="")
    with pytest.raises(Exception):
        _v2(description="")


def test_v2_accepts_optional_logo_urls():
    v2 = _v2(
        agent=MakeMovieAgent(id=42, name="Maria Silva", logo_url="https://cdn/agent.png"),
        kondo=MakeMovieKondo(
            id=7001,
            address="Rua X, 1",
            brokerage_logo_url="https://cdn/broker.png",
        ),
    )
    legacy = v2_to_legacy_request(v2)
    # legacy MakeMovieRequest doesn't carry logos today — they're dropped on
    # translation. This is intentional: those will be wired into the
    # MovieModel when the engine grows brand-card support.
    assert legacy.request_id.user.id == "42"


def test_translation_passes_agent_name_through():
    legacy = v2_to_legacy_request(_v2())
    # Stateless flow: agent name comes from the request, no Firestore lookup.
    assert legacy.agent_name == "Maria Silva"


def test_v2_music_url_is_captured_but_not_yet_mapped():
    # Forward-compat: music_url is part of the contract but the engine
    # doesn't yet have a per-render music override. The translation
    # silently accepts it — this test pins that behavior so a future
    # change has to consciously update both places.
    legacy = v2_to_legacy_request(_v2(music_url="https://cdn/music.mp3"))
    # No assertion on legacy carrying music_url — there's no field for it
    # yet. Reaching this line without raising is the contract.
    assert legacy.template == "city_beat"
