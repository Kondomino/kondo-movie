from pathlib import Path
from config.config import settings
from logger import logger
from movie_maker.edl_model import ClipTypeEnum
import os

_BUNDLED_FONTS_DIR = Path(__file__).resolve().parents[2] / "library" / "fonts"


class FontManager:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._font_cache = {}
        
    def _get_font_name_for_clip_type(self, clip_type: ClipTypeEnum) -> str:
        """Map clip type to font filename"""
        font_mapping = {
            ClipTypeEnum.AGENT_NAME: "AgentName.ttf",
            ClipTypeEnum.ADDRESS: "Address.ttf",
            ClipTypeEnum.PROPERTY_LOCATION: "PropertyLocation.ttf",
            # KONDO_ADDRESS / KONDO_LOCALITY share fonts with their non-Kondo
            # counterparts — same visual register, different text source.
            ClipTypeEnum.KONDO_ADDRESS: "Address.ttf",
            ClipTypeEnum.KONDO_LOCALITY: "PropertyLocation.ttf",
            ClipTypeEnum.OCCASION_TEXT: "OccasionTitle.ttf",
            ClipTypeEnum.OCCASION_SUBTITLE: "OccasionSubtitle.ttf",
            ClipTypeEnum.TITLE: "Title.ttf",
            ClipTypeEnum.PRESENTS: "Presents.ttf",
        }
        return font_mapping.get(clip_type, "Default.ttf")
    
    def _get_default_font_for_clip_type(self, clip_type: ClipTypeEnum) -> str:
        """Get default font for each clip type"""
        default_fonts = {
            ClipTypeEnum.AGENT_NAME: settings.MovieMaker.EndTitles.Main.Font.NAME,
            ClipTypeEnum.ADDRESS: "GothamOffice-Regular.otf",
            ClipTypeEnum.PROPERTY_LOCATION: "Gotham-Light.otf",
            ClipTypeEnum.KONDO_ADDRESS: "GothamOffice-Regular.otf",
            ClipTypeEnum.KONDO_LOCALITY: "Gotham-Light.otf",
            ClipTypeEnum.OCCASION_TEXT: "GothamOffice-Regular.otf",
            ClipTypeEnum.OCCASION_SUBTITLE: "Gotham-Light.otf",
            ClipTypeEnum.TITLE: settings.MovieMaker.EndTitles.Main.Font.NAME,
            ClipTypeEnum.PRESENTS: settings.MovieMaker.EndTitles.Main.Font.NAME,
        }
        name = default_fonts.get(clip_type, settings.MovieMaker.EndTitles.Main.Font.NAME)
        # Resolve to absolute path under library/fonts/ so PIL can load it.
        # The bare filename only worked when GCP fonts bucket was reachable;
        # with the engine stateless we always fall through to bundled fonts.
        return str(_BUNDLED_FONTS_DIR / name)
    
    def get_font_path(self, clip_type: ClipTypeEnum) -> str:
        """
        Resolve a font path for the given clip type.

        v1: per-user custom fonts are not a kondomino feature — every
        agent uses the bundled fonts under `library/fonts/`. The legacy
        path that fetched `gs://editora-v2-users/{user_id}/fonts/...`
        was disconnected here in 2026-04-28 to silence the per-render
        GCP error spam (one log line per clip type, every render). When
        per-agent fonts come back they'll be served from R2, not GCP.
        """
        if clip_type in self._font_cache:
            return self._font_cache[clip_type]

        default_font = self._get_default_font_for_clip_type(clip_type)
        self._font_cache[clip_type] = default_font
        return default_font

    def cleanup_temp_fonts(self):
        """No-op in v1: bundled-only paths are stable filesystem entries."""
        self._font_cache.clear()