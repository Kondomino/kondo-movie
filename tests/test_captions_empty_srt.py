"""
Pin the empty-SRT guard in CaptionsManager.

Background: when AssemblyAI is disabled (free-tier deploy) and OpenAI
transcription either errors or isn't wired, Transcriber_Mock writes an
empty SRT file. moviepy's SubtitlesClip then crashes with
`max() iterable argument is empty` from inside its parser, which
manifests as a render failure with no useful breadcrumb. This test
locks in the safer behavior: empty SRT → return (None, path) so the
caller can skip the caption clip and proceed with audio-only narration.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from movie_maker.captions import CaptionsManager


class _NoopTranscriber:
    """Stand-in for Transcriber that simulates Transcriber_Mock —
    writes nothing to the SRT file the way the real mock does."""

    def __init__(self, *_, **__):
        pass

    def generate_captions_from_voiceover(self, voiceover_file_path, srt_file):
        # Mirror Transcriber_Mock: write empty + close.
        srt_file.write("")
        srt_file.close()


def test_generate_captions_returns_none_when_srt_is_empty(tmp_path):
    # Patch the Transcriber the manager constructs so we don't need the
    # real ai/transcriber stack (which pulls feature flags + API keys).
    with patch("movie_maker.captions.Transcriber", _NoopTranscriber):
        manager = CaptionsManager(resolution=(1920, 1080))
        # Voiceover path doesn't matter — the noop transcriber ignores it.
        with NamedTemporaryFile(suffix=".wav", delete=False) as fake_voiceover:
            subtitles, srt_path = manager.generate_captions(
                voiceover_file_path=fake_voiceover.name,
            )

    assert subtitles is None, "empty SRT must short-circuit before SubtitlesClip"
    assert isinstance(srt_path, Path)
    assert srt_path.stat().st_size == 0
