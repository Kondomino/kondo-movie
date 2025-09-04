from tempfile import NamedTemporaryFile
from pathlib import Path
import textwrap

from moviepy import TextClip
from moviepy.video.tools.subtitles import SubtitlesClip

from logger import logger
from config.config import settings
from ai.transcriber import Transcriber


class CaptionsManager:
    def __init__(self, resolution: tuple, srt_file_path: Path = None):
        self.resolution = resolution
        self.transcriber = Transcriber(
            max_char_per_segment=settings.MovieMaker.Narration.Captions.MAX_CHARS_PER_SRT_SEGMENT
        )

        if not srt_file_path:
            self.srt_file = NamedTemporaryFile(
                mode="w+t", suffix=".srt", delete=False, delete_on_close=False
            )
            self.srt_file_path = Path(self.srt_file.name)
        else:
            self.srt_file_path = srt_file_path
            self.srt_file = open(file=self.srt_file_path, mode="w+t")

    def generate_captions(self, voiceover_file_path: str) -> tuple[SubtitlesClip, Path]:
        self.transcriber.generate_captions_from_voiceover(
            voiceover_file_path=voiceover_file_path, srt_file=self.srt_file
        )

        generator = lambda txt: TextClip(
            text=textwrap.fill(
                txt,
                width=settings.MovieMaker.Narration.Captions.TEXTWRAP_MAX_CHARS_PER_LINE,
            ),
            font=settings.MovieMaker.Narration.Captions.Font.NAME,
            font_size=settings.MovieMaker.Narration.Captions.Font.SIZE,
            color=settings.MovieMaker.Narration.Captions.Font.COLOR,
            bg_color=settings.MovieMaker.Narration.Captions.Background.COLOR,
            margin=settings.MovieMaker.Narration.Captions.FONT_MARGIN,
            text_align="center",
        )
        height_factor = (
            settings.MovieMaker.Narration.Captions.HEIGHT_FACTOR_PORTRAIT
            if self.resolution == settings.MovieMaker.Video.RESOLUTION_PORTRAIT
            else settings.MovieMaker.Narration.Captions.HEIGHT_FACTOR_LANDSCAPE
        )
        subtitles = (
            SubtitlesClip(subtitles=self.srt_file_path, make_textclip=generator)
            .with_opacity(settings.MovieMaker.Narration.Captions.OPACITY)
            .with_position(
                lambda clip: (
                    settings.MovieMaker.Narration.Captions.ALIGNMENT,
                    self.resolution[1] * height_factor,
                )
            )
            .with_start(
                voiceover_offset or settings.MovieMaker.Narration.Voiceover.START_OFFSET
            )
        )

        return (subtitles, self.srt_file_path)
