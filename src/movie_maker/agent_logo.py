from moviepy import ColorClip
from config.config import settings
from movie_maker.edl_model import Clip
from movie_maker.effects import Effects
from movie_maker.edl_manager import EDLUtils
from movie_maker.movie_model import MovieModel


class AgentLogoManager():
    """
    Agent-logo clip generator.

    v1 status: HARD-DISCONNECTED. The legacy implementation fetched a
    per-agent PNG from `gs://editora-v2-users/{user_id}/logos/agent_white.png`
    via the GCP storage adapter. The kondomino User row has no logo URL
    today and the GCP path is dead — when logos come back they'll be
    served from `media.kondomino.com.br/agents/<id>/...` (R2). Until
    then, `_get_logo_path` raises `FileNotFoundError` cleanly so the
    `try/except` at `video_generation._generate_multiple_clips` skips
    the AgentLogo clip without a noisy GCP traceback.
    """

    def __init__(self, resolution: tuple, fps: int, user_id: str):
        self.resolution = resolution
        self.fps = fps
        self.user_id = user_id

    def _get_logo_path(self, orientation: MovieModel.Configuration.Orientation) -> str:
        # Disconnected in v1 — see class docstring.
        raise FileNotFoundError(
            "Agent logo is disabled in v1 (no per-agent assets shipped yet)"
        )

    def generate_agent_logo(
        self,
        clip_start_time: float,
        edl_clip: Clip,
        orientation: MovieModel.Configuration.Orientation,
    ) -> tuple[list, float]:
        """
        Background-only fallback path for the standalone AgentLogo clip
        type. Returns the background ColorClip + transition frames; the
        actual logo overlay is skipped because `_get_logo_path` raises
        unconditionally in v1. Kept as a no-op-ish shape so EDL parsing
        and the rest of the renderer don't have to special-case the
        disabled state.
        """
        agent_logo_clips: list = []
        clip_duration = EDLUtils.duration_to_seconds(duration=edl_clip.duration, fps=self.fps)
        RESOLUTION = self.resolution

        if edl_clip.transition_in and edl_clip.transition_in.transition_frame is True:
            black_frame, clip_start_time = Effects.black_frame(
                fps=self.fps, resolution=RESOLUTION, start_time=clip_start_time
            )
            agent_logo_clips.append(black_frame)

        background_clip = ColorClip(
            size=RESOLUTION,
            color=settings.MovieMaker.EndTitles.General.BG_COLOR,
        ).with_start(clip_start_time).with_duration(clip_duration)
        background_clip = Effects.apply_transition(
            clip=background_clip, edl_clip=edl_clip, fps=self.fps
        )
        agent_logo_clips.append(background_clip)

        clip_start_time += clip_duration

        if edl_clip.transition_out and edl_clip.transition_out.transition_frame is True:
            black_frame, clip_start_time = Effects.black_frame(
                fps=self.fps, resolution=RESOLUTION, start_time=clip_start_time
            )
            agent_logo_clips.append(black_frame)

        return agent_logo_clips, clip_start_time
