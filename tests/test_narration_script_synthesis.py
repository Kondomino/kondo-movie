"""
Unit-level coverage for MovieMaker._synthesize_default_script — the
fallback path that fires when the caller (kondos-api wizard today) leaves
narration enabled but supplies no description. Without this, the
movie.py:99 `if narration.enabled and narration.script:` guard silently
skipped TTS and produced silent video.

These tests poke the helper directly with a stubbed MovieModel so they
don't need the renderer + EDL stack. A monkeypatched ScriptManager keeps
the suite hermetic (no OpenAI calls).
"""

from unittest.mock import MagicMock

import pytest

from movie_maker.movie import MovieMaker
from movie_maker.movie_model import MovieModel


def _stub_movie_model(
    *,
    kondo_name: str | None = None,
    address1: str | None = None,
    address2: str | None = None,
    agent_name: str | None = None,
) -> MovieModel:
    """Build a minimal MovieModel that satisfies the synthesis helper's
    field reads. The fields the helper doesn't touch can be cheap stubs."""
    model = MovieModel.model_construct(
        edl=None,
        ordered_images=[],
        config=MovieModel.Configuration(),
        user_id="42",
        agent_name=agent_name,
        kondo_name=kondo_name,
        kondo_address_line1=address1,
        kondo_address_line2=address2,
    )
    return model


def _maker(model: MovieModel) -> MovieMaker:
    """MovieMaker.__init__ reads config.image_orientation; that's safe with
    the default Configuration. We bypass the rest of the constructor work."""
    return MovieMaker(movie_model=model)


def test_synthesizes_brief_when_kondo_name_present(monkeypatch):
    # Stub ScriptManager so the test stays hermetic — assert that the brief
    # we'd send to OpenAI carries the kondo identity.
    captured: dict = {}

    class FakeScriptManager:
        def generate_script(self, description: str) -> str:
            captured["brief"] = description
            return "Aretê Búzios em Búzios — uma joia do litoral."

    monkeypatch.setattr("movie_maker.movie.ScriptManager", FakeScriptManager)

    maker = _maker(
        _stub_movie_model(
            kondo_name="Aretê Búzios",
            address1="Manguinhos",
            address2="Búzios, RJ",
            agent_name="Maria Silva",
        )
    )
    script = maker._synthesize_default_script()

    assert script == "Aretê Búzios em Búzios — uma joia do litoral."
    assert "Aretê Búzios" in captured["brief"]
    assert "Manguinhos" in captured["brief"]
    assert "Maria Silva" in captured["brief"]


def test_returns_empty_when_no_context(monkeypatch):
    # No kondo name, no address, no agent name → there's nothing meaningful
    # to narrate. Better silent than a "we have no idea what this is" script.
    monkeypatch.setattr(
        "movie_maker.movie.ScriptManager",
        MagicMock(side_effect=AssertionError("ScriptManager should not be called")),
    )
    maker = _maker(_stub_movie_model())
    assert maker._synthesize_default_script() == ""


def test_falls_back_to_brief_when_script_manager_raises(monkeypatch):
    # Defensive: if OpenAI throws, we still want a script (even rough) so
    # the video isn't silent. Brief verbatim is acceptable — better some
    # narration than none.
    class ExplodingScriptManager:
        def generate_script(self, description: str) -> str:
            raise RuntimeError("openai unavailable")

    monkeypatch.setattr("movie_maker.movie.ScriptManager", ExplodingScriptManager)

    maker = _maker(_stub_movie_model(kondo_name="Aretê Búzios"))
    script = maker._synthesize_default_script()
    assert "Aretê Búzios" in script


def test_handles_only_address(monkeypatch):
    # Old kondo records may have addresses but no name. The brief should
    # still synthesize something meaningful.
    captured: dict = {}

    class FakeScriptManager:
        def generate_script(self, description: str) -> str:
            captured["brief"] = description
            return "Localização privilegiada."

    monkeypatch.setattr("movie_maker.movie.ScriptManager", FakeScriptManager)

    maker = _maker(
        _stub_movie_model(
            address1="Rua das Pedras",
            address2="Búzios, RJ",
        )
    )
    script = maker._synthesize_default_script()

    assert script == "Localização privilegiada."
    assert "Rua das Pedras" in captured["brief"]
    assert "Búzios" in captured["brief"]
