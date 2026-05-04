"""
Kondomino brand watermark — applied bottom-right on every rendered movie.

Always-on by default (the engine's `MovieModel.config.watermark` defaults to
True post-2026-05-04). The asset is bundled in the engine image at
`library/logo/kondomino_watermark.png` (Dockerfile copies `library/logo/`
into `/library/logo/` at build time). No GCP/R2 fetch — the watermark is
immutable brand identity, baked into the deploy.

Future "premium remove watermark" feature will:
  - add `remove_watermark: bool` to MakeMovieRequest.capabilities
  - kondos-api gates it on a Capability (e.g. VIDEO_NO_WATERMARK)
  - the v2 translator passes it through to MovieModel.config.watermark = not remove
  - this module is unchanged

Why local-bundled rather than fetched-from-URL: it's a single immutable
asset that ships with the engine, fetching it per render would be wasted
bytes + a fragility surface. To swap the watermark, redeploy.
"""

from pathlib import Path

from moviepy import ImageClip

from config.config import settings
from logger import logger


class Watermark:
    """Bottom-right Kondomino brand mark, sized + positioned per resolution."""

    # Bundled-asset root: `<repo>/library/logo/<filename>`.
    # `library/` sits next to `src/`, so we go up three from this file
    # (movie_maker → src → repo root) and join — same pattern as
    # `EDLManager._TEMPLATES_ROOT`.
    _LOGO_ROOT = (
        Path(__file__).resolve().parent.parent.parent / "library" / "logo"
    )

    def __init__(self, resolution: tuple, duration: float):
        self.RESOLUTION = resolution
        self.duration = duration

    def _resolve_watermark_path(self) -> Path:
        """Resolve the bundled watermark path. Raises if missing — fail loudly
        because a missing watermark is a deploy regression, not a per-render
        condition we should silently swallow."""
        filename = settings.MovieMaker.Watermark.DEFAULT
        path = self._LOGO_ROOT / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"Kondomino watermark not found at {path}. The engine image "
                "must include `library/logo/<filename>` per Dockerfile."
            )
        return path

    def generate_watermark_clip(self) -> ImageClip:
        """Build the watermark overlay clip for the current movie."""
        watermark_path = self._resolve_watermark_path()
        logger.info(f"[WATERMARK] Loading from {watermark_path}")

        watermark = ImageClip(str(watermark_path)).with_duration(self.duration)

        is_portrait = self.RESOLUTION == settings.MovieMaker.Video.RESOLUTION_PORTRAIT
        size_by_height = (
            settings.MovieMaker.Watermark.SIZE_BY_HEIGHT_PORTRAIT
            if is_portrait
            else settings.MovieMaker.Watermark.SIZE_BY_HEIGHT_LANDSCAPE
        )
        watermark = watermark.resized(height=size_by_height)

        pixel_offset_width = (
            settings.MovieMaker.Watermark.PIXEL_OFFSET_WIDTH_PORTRAIT
            if is_portrait
            else settings.MovieMaker.Watermark.PIXEL_OFFSET_WIDTH_LANDSCAPE
        )
        pixel_offset_height = (
            settings.MovieMaker.Watermark.PIXEL_OFFSET_HEIGHT_PORTRAIT
            if is_portrait
            else settings.MovieMaker.Watermark.PIXEL_OFFSET_HEIGHT_LANDSCAPE
        )

        watermark_position = (
            self.RESOLUTION[0] - watermark.w - pixel_offset_width,
            self.RESOLUTION[1] - watermark.h - pixel_offset_height,
        )
        watermark = watermark.with_position(watermark_position).with_opacity(
            settings.MovieMaker.Watermark.OPACITY
        )

        return watermark
