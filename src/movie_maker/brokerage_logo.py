from moviepy import ColorClip
from config.config import settings
from movie_maker.edl_model import Clip
from movie_maker.effects import Effects
from movie_maker.edl_manager import EDLUtils
from movie_maker.movie_model import MovieModel


class BrokerageLogoManager():
    """
    Brokerage-logo clip generator.

    v1 status: HARD-DISCONNECTED per Victor 2026-04-28. Kondomino's
    branding is platform-level (single tenant); we don't render
    brokerage marks on the videos in v1. The legacy implementation
    fetched `gs://editora-v2-users/{user_id}/brokerage-assets/landscape.png`
    from the GCS USER_BUCKET — that whole path is gone. Re-enables when
    multi-tenant branding lands (no concrete plan today).

    `_get_logo_path` raises `FileNotFoundError` cleanly so the
    `try/except` at `video_generation._generate_multiple_clips` skips
    the BrokerageLogo clip without a noisy GCP traceback.
    """

    def __init__(self, resolution: tuple, fps: int, user_id: str):
        self.resolution = resolution
        self.fps = fps
        self.user_id = user_id

    def _get_logo_path(self, orientation: MovieModel.Configuration.Orientation) -> str:
        # Disconnected in v1 — see class docstring.
        raise FileNotFoundError(
            "Brokerage logo is disabled in v1 (kondomino-only branding)"
        )

    def generate_brokerage_logo(
        self,
        clip_start_time: float,
        edl_clip: Clip,
        orientation: MovieModel.Configuration.Orientation,
    ) -> tuple[list, float]:
        """
        Background-only fallback path for the standalone BrokerageLogo
        clip type. Returns the background ColorClip + transition frames;
        the actual logo overlay is skipped because `_get_logo_path`
        raises unconditionally in v1.
        """
        brokerage_logo_clips: list = []
        clip_duration = EDLUtils.duration_to_seconds(duration=edl_clip.duration, fps=self.fps)
        RESOLUTION = self.resolution

        if edl_clip.transition_in and edl_clip.transition_in.transition_frame is True:
            black_frame, clip_start_time = Effects.black_frame(
                fps=self.fps, resolution=RESOLUTION, start_time=clip_start_time
            )
            brokerage_logo_clips.append(black_frame)

        background_clip = ColorClip(
            size=RESOLUTION,
            color=settings.MovieMaker.EndTitles.General.BG_COLOR,
        ).with_start(clip_start_time).with_duration(clip_duration)
        background_clip = Effects.apply_transition(
            clip=background_clip, edl_clip=edl_clip, fps=self.fps
        )
        brokerage_logo_clips.append(background_clip)

        clip_start_time += clip_duration

        if edl_clip.transition_out and edl_clip.transition_out.transition_frame is True:
            black_frame, clip_start_time = Effects.black_frame(
                fps=self.fps, resolution=RESOLUTION, start_time=clip_start_time
            )
            brokerage_logo_clips.append(black_frame)

        return brokerage_logo_clips, clip_start_time
