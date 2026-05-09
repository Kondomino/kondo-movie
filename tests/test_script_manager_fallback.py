"""
Pin the verbatim-fallback in ScriptManager.

Background: when OpenAI is unavailable (account-quota exhaustion is the
current prod state on the engine, but the path also fires for service
disable + repeated char-cap blowouts), ScriptManager has to return a
script anyway so the render isn't silent. The previous fallback wrapped
the brief in a literal English `"Property description: ..."` prefix
that ElevenLabs then narrated verbatim into the final video — surfaced
as user feedback 2026-05-09. The new behavior returns the brief
verbatim (or truncated, never wrapped).
"""

from ai.script_manager import _fallback_script, _FALLBACK_MAX_CHARS


def test_short_brief_returned_verbatim():
    brief = "Aretê Búzios. Situado em Manguinhos, Búzios, RJ. Apresentado por Maria Silva."
    assert _fallback_script(brief) == brief


def test_no_english_prefix_leaks():
    # The original bug: the fallback wrapped briefs in
    # "Property description: <truncated>..." which got narrated
    # verbatim. Pin that this prefix never appears in the output.
    assert "Property description" not in _fallback_script(
        "Some pt-BR brief that happens to be 50 chars long ok",
    )


def test_long_brief_truncated_with_ellipsis():
    # Defensive cap so a runaway brief from a future caller doesn't pile
    # up ElevenLabs spend. The synthesized briefs from
    # MovieMaker._synthesize_default_script cap at ~250 chars in
    # practice — well under _FALLBACK_MAX_CHARS.
    brief = "x" * (_FALLBACK_MAX_CHARS + 50)
    out = _fallback_script(brief)
    assert out.endswith("...")
    assert len(out) == _FALLBACK_MAX_CHARS + 3  # "..." appended


def test_strips_whitespace():
    assert _fallback_script("   hello world  \n") == "hello world"


def test_handles_empty_input():
    assert _fallback_script("") == ""
    assert _fallback_script(None) == ""  # type: ignore[arg-type]
