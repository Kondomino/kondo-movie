from moviepy import TextClip, ColorClip

from config.config import settings
from logger import logger
from movie_maker.edl_model import Clip, ClipTypeEnum, Duration, Transform
from movie_maker.effects import Effects
from movie_maker.edl_manager import EDLUtils


class PresentsManager:
    def __init__(self, resolution: tuple, fps: int, font_manager=None):
        self.resolution = resolution
        self.fps = fps
        self.font_manager = font_manager

    def generate_presents(
        self,
        clip_start_time: float,
        edl_clip: Clip,
        text_font_size: int | None = None,
        enable_background: bool = True,
        text_start_time: None | float = None,
        text_duration: None | Duration = None,
        text_vfx_array: list[any] | None = None,
        transform: None | Transform = None,
    ) -> tuple[list, float]:
        presents_clips = []
        clip_duration = EDLUtils.duration_to_seconds(
            duration=edl_clip.duration, fps=self.fps
        )
        if not text_font_size:
            text_font_size = settings.MovieMaker.EndTitles.Main.Font.SIZE
        RESOLUTION = self.resolution

        # Step 1 - Add pre-transition frame
        if edl_clip.transition_in and edl_clip.transition_in.transition_frame == True:
            black_frame, clip_start_time = Effects.black_frame(
                fps=self.fps, resolution=RESOLUTION, start_time=clip_start_time
            )
            presents_clips.append(black_frame)

        # Step 2 - Add background clip
        background_clip = (
            ColorClip(
                size=RESOLUTION, color=settings.MovieMaker.EndTitles.General.BG_COLOR
            )
            .with_start(clip_start_time)
            .with_duration(clip_duration)
        )
        background_clip = Effects.apply_transition(
            clip=background_clip, edl_clip=edl_clip, fps=self.fps
        )

        # Step 3 - Add presents text
        text = "PRESENTS"

        # Calculate text position and size
        text_size_y = settings.MovieMaker.EndTitles.Main.LINE_SIZE
        text_start_y = RESOLUTION[1] / 2 - text_size_y / 2
        text_size_x = (
            RESOLUTION[0]
            - 2 * settings.MovieMaker.EndTitles.Geometry.Landscape.H_MARGIN
            if RESOLUTION[0] > RESOLUTION[1]
            else RESOLUTION[0]
            - 2 * settings.MovieMaker.EndTitles.Geometry.Portrait.H_MARGIN
        )
        text_start_x = (
            settings.MovieMaker.EndTitles.Geometry.Landscape.H_MARGIN
            if RESOLUTION[0] > RESOLUTION[1]
            else settings.MovieMaker.EndTitles.Geometry.Portrait.H_MARGIN
        )

        # Create TextClip for the presents text
        if transform and transform.x_offset:
            text_start_x = text_start_x + transform.x_offset
        if transform and transform.y_offset:
            text_start_y = text_start_y + transform.y_offset

        text_duration_seconds = clip_duration
        if text_duration:
            text_duration_seconds = text_duration.to_seconds(fps=self.fps)

        presents_font = self.font_manager.get_font_path(ClipTypeEnum.PRESENTS) if self.font_manager else "GothamOffice-Regular.otf"
        text_clip = (
            TextClip(
                text=text,
                font_size=text_font_size,
                size=(text_size_x, text_size_y),
                font=presents_font,
                color=settings.MovieMaker.EndTitles.Main.Font.COLOR,
                margin=settings.MovieMaker.EndTitles.Main.FONT_MARGIN,
                method=settings.MovieMaker.EndTitles.General.METHOD,
                text_align=settings.MovieMaker.EndTitles.General.ALIGNMENT,
            )
            .with_start(text_start_time or clip_start_time)
            .with_duration(text_duration_seconds)
            .with_position((text_start_x, text_start_y))
        )
        if text_vfx_array:
            text_clip = text_clip.with_effects(text_vfx_array)

        # Add transitions if necessary
        text_clip = Effects.apply_transition(
            clip=text_clip, edl_clip=edl_clip, fps=self.fps
        )

        # Step 4 - Append background & text clips
        if enable_background:
            presents_clips.append(background_clip)
        presents_clips.append(text_clip)

        # Step 5 - Update start time
        clip_start_time += clip_duration

        # Step 6 - Add post-transition frame
        if edl_clip.transition_out and edl_clip.transition_out.transition_frame == True:
            black_frame, clip_start_time = Effects.black_frame(
                fps=self.fps, resolution=RESOLUTION, start_time=clip_start_time
            )

        return presents_clips, clip_start_time
