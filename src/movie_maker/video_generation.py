import traceback
import pillow_avif  # IMPORTANT : Need this import to support .avif files

import math

from logger import logger
from config.config import settings

from movie_maker.edl_model import (
    EDL,
    ClipTypeEnum,
    ClipEffectEnum,
    MultipleClip,
    PositionEnum,
    Clip,
    Duration,
)
from movie_maker.edl_manager import EDLUtils
from movie_maker.movie_model import MovieModel
from movie_maker.end_titles import EndTitleManager
from movie_maker.effects import Effects
from movie_maker.presents import PresentsManager
from movie_maker.agent_logo import AgentLogoManager
from movie_maker.brokerage_logo import BrokerageLogoManager
from movie_maker.font_manager import FontManager

from moviepy import ImageClip, TextClip, ColorClip, vfx

import re


def expand_abbreviations(text: str, mapping: dict) -> str:
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in mapping.keys()) + r")\b", re.IGNORECASE
    )
    return pattern.sub(lambda m: mapping[m.group().lower()], text)


ABBREVIATIONS = {
    "aly": "Alley",
    "ave": "Avenue",
    "blvd": "Boulevard",
    "brg": "Bridge",
    "cir": "Circle",
    "ct": "Court",
    "dr": "Drive",
    "expy": "Expressway",
    "hwy": "Highway",
    "ln": "Lane",
    "loop": "Loop",
    "mtwy": "Motorway",
    "pkwy": "Parkway",
    "pl": "Place",
    "plz": "Plaza",
    "rd": "Road",
    "sq": "Square",
    "st": "Street",
    "ter": "Terrace",
    "trl": "Trail",
    "tpke": "Turnpike",
    "walk": "Walk",
    "way": "Way",
}


class VideoGenerator:
    def __init__(
        self, edl: EDL, ordered_images: list[str], movie_model: MovieModel, resolution
    ):
        self.edl = edl
        self.ordered_images = ordered_images
        self.movie_model = movie_model
        self.RESOLUTION = resolution
        self.font_manager = FontManager(user_id=movie_model.user_id)

    def _image_path_for_index(self, index: int):

        if index < len(self.ordered_images):
            return self.ordered_images[index]
        else:
            error_log = f"Only {len(self.ordered_images)} image files provided. Not enough images to make video"
            logger.error(error_log)
            raise FileNotFoundError(error_log)

    def _generate_multiple_clips(
        self,
        base_clip,
        multiple_clips: list[MultipleClip],
        clip_start_time: float,
        clip_duration: Duration,
        fps: int,
    ) -> list:
        """Generate clips to overlay on the base image clip"""
        overlay_clips = []
        RESOLUTION = self.RESOLUTION

        # Calculate caption height if captions are enabled
        caption_height = 0
        if (
            self.movie_model.config.narration
            and self.movie_model.config.narration.captions
        ):
            # Calculate caption height based on font size and margins
            caption_font_size = settings.MovieMaker.Narration.Captions.Font.SIZE
            caption_margin = settings.MovieMaker.Narration.Captions.FONT_MARGIN
            caption_height = (
                caption_font_size + caption_margin[1] * 2
            )  # Add vertical margins

        height_factor = (
            settings.MovieMaker.Narration.Captions.HEIGHT_FACTOR_PORTRAIT
            if RESOLUTION == settings.MovieMaker.Video.RESOLUTION_PORTRAIT
            else settings.MovieMaker.Narration.Captions.HEIGHT_FACTOR_LANDSCAPE
        )
        caption_top = int(RESOLUTION[1] * height_factor)
        available_height = caption_top
        section_height = available_height / 3

        for multiple_clip in multiple_clips:

            multiple_clip_start_time: float = clip_start_time
            multiple_clip_duration: Duration = clip_duration

            vfx_array = []
            if multiple_clip.fade_in:
                vfx_array.append(vfx.CrossFadeIn(multiple_clip.fade_in.frames / fps))
            if multiple_clip.fade_out:
                vfx_array.append(vfx.CrossFadeOut(multiple_clip.fade_out.frames / fps))

            if multiple_clip.start:
                assert multiple_clip.end, "Start time is provided without end time"
                multiple_clip_start_time = multiple_clip.start.to_seconds(fps=fps)
                multiple_clip_duration = Duration.from_seconds(
                    seconds=multiple_clip.end.to_seconds(fps=fps)
                    - multiple_clip_start_time,
                    fps=fps,
                )

            if multiple_clip.clip_type in [
                ClipTypeEnum.AGENT_NAME,
                ClipTypeEnum.ADDRESS,
                ClipTypeEnum.PROPERTY_LOCATION,
                ClipTypeEnum.OCCASION_TEXT,
                ClipTypeEnum.OCCASION_SUBTITLE,
            ]:
                # Create text clip for agent name
                text: str = ""

                if multiple_clip.clip_type == ClipTypeEnum.AGENT_NAME:
                    # Skip AGENT_NAME clip if agent_presents is disabled
                    if not getattr(self.movie_model.config, "agent_presents", None):
                        continue
                    text = getattr(self.movie_model, "agent_name", None)
                elif multiple_clip.clip_type == ClipTypeEnum.ADDRESS:
                    # Check if this clip contains OccasionText to determine if we should apply validation
                    has_occasion_text_in_clip = any(
                        clip.clip_type == ClipTypeEnum.OCCASION_TEXT 
                        for clip in multiple_clips
                    )
                    
                    # Only validate if there's OccasionText in the same clip 
                    if (has_occasion_text_in_clip and 
                        self.movie_model.config.occasion and 
                        self.movie_model.config.occasion.enabled and 
                        self.movie_model.config.occasion.occasion):
                        # Skip address clip if occasion text is available
                        continue
                    
                    # Use main_title if available, otherwise use a generic fallback
                    if self.movie_model.config.end_titles and self.movie_model.config.end_titles.main_title:
                        text: str = self.movie_model.config.end_titles.main_title
                    else:
                        # Generic fallback for when main_title is None
                        text: str = "PROPERTY ADDRESS"
                        logger.warning("Using generic fallback for ADDRESS clip: main_title is None")
                        
                    text = expand_abbreviations(text, ABBREVIATIONS)
                elif (
                    multiple_clip.clip_type == ClipTypeEnum.PROPERTY_LOCATION
                ):
                    # Use sub_title if available, otherwise use a generic fallback
                    if self.movie_model.config.end_titles and self.movie_model.config.end_titles.sub_title:
                        text: str = self.movie_model.config.end_titles.sub_title
                    else:
                        # Generic fallback for when sub_title is None
                        text: str = "PROPERTY DETAILS"
                        logger.warning("Using generic fallback for PROPERTY_LOCATION clip: sub_title is None")
                elif multiple_clip.clip_type == ClipTypeEnum.OCCASION_TEXT:
                    # Handle occasion text from config - renders occasion.occasion
                    if (self.movie_model.config.occasion and 
                        self.movie_model.config.occasion.enabled and 
                        self.movie_model.config.occasion.occasion):
                        text = self.movie_model.config.occasion.occasion
                    else:
                        # Skip this clip if occasion is not enabled or text is empty
                        continue
                elif multiple_clip.clip_type == ClipTypeEnum.OCCASION_SUBTITLE:
                    # Handle occasion subtitle from config - renders occasion.subtitle
                    if (self.movie_model.config.occasion and 
                        self.movie_model.config.occasion.enabled and 
                        self.movie_model.config.occasion.subtitle):
                        text = self.movie_model.config.occasion.subtitle
                    else:
                        # Skip this clip if occasion is not enabled or subtitle is empty
                        continue
                else:
                    raise ValueError(f"Invalid clip type: {multiple_clip.clip_type}")

                # Get custom font for this clip type
                font = self.font_manager.get_font_path(multiple_clip.clip_type)

                text_size_y = settings.MovieMaker.EndTitles.Main.LINE_SIZE
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

                if multiple_clip.position == PositionEnum.TOP:
                    text_start_y = section_height / 2 - text_size_y / 2
                elif multiple_clip.position == PositionEnum.CENTER:
                    text_start_y = available_height / 2 - text_size_y / 2
                else:
                    text_start_y = (
                        available_height - section_height / 2 - text_size_y / 2
                    )

                # Use custom font_size if provided, otherwise use default
                font_size = getattr(
                    multiple_clip,
                    "font_size",
                    settings.MovieMaker.EndTitles.Main.Font.SIZE,
                )

                if multiple_clip.transform and multiple_clip.transform.x_offset:
                    text_start_x = text_start_x + multiple_clip.transform.x_offset
                if multiple_clip.transform and multiple_clip.transform.y_offset:
                    text_start_y = text_start_y + multiple_clip.transform.y_offset

                text_clip = (
                    TextClip(
                        text=text.upper(),
                        font_size=font_size,
                        size=(text_size_x, text_size_y),
                        font=font,
                        color=settings.MovieMaker.EndTitles.Main.Font.COLOR,
                        margin=settings.MovieMaker.EndTitles.Main.FONT_MARGIN,
                        method=settings.MovieMaker.EndTitles.General.METHOD,
                        text_align=settings.MovieMaker.EndTitles.General.ALIGNMENT,
                        interline=settings.MovieMaker.Text.LETTER_SPACING,
                    )
                    .with_start(multiple_clip_start_time)
                    .with_duration(
                        multiple_clip_duration.to_seconds(fps=fps)
                        if multiple_clip_duration
                        else clip_duration.to_seconds(fps=fps)
                    )
                    .with_position((text_start_x, text_start_y))
                )
                if vfx_array:
                    text_clip = text_clip.with_effects(vfx_array)

                overlay_clips.append(text_clip)

            elif multiple_clip.clip_type in [
                ClipTypeEnum.AGENT_LOGO,
                ClipTypeEnum.BROKERAGE_LOGO,
            ]:
                # Get appropriate logo manager
                logo_manager = (
                    AgentLogoManager(
                        resolution=RESOLUTION, fps=fps, user_id=self.movie_model.user_id
                    )
                    if multiple_clip.clip_type == ClipTypeEnum.AGENT_LOGO
                    else BrokerageLogoManager(
                        resolution=RESOLUTION, fps=fps, user_id=self.movie_model.user_id
                    )
                )

                # Get logo path
                try:
                    logo_path = logo_manager._get_logo_path(
                        self.movie_model.config.image_orientation
                    )
                    logo_clip = ImageClip(logo_path)

                    # Calculate logo size and position
                    logo_width, logo_height = logo_clip.size
                    aspect_ratio = logo_width / logo_height
                    # Calculate max dimensions based on section height
                    if RESOLUTION[0] > RESOLUTION[1]:
                        max_width = RESOLUTION[0] - settings.MovieMaker.EndTitles.Geometry.Landscape.H_MARGIN
                        max_height = section_height - settings.MovieMaker.EndTitles.Geometry.Landscape.V_MARGIN
                    else:
                        max_width = RESOLUTION[0] * 0.40
                        max_height = section_height * 0.40

                    # Calculate new dimensions maintaining aspect ratio
                    if logo_width / max_width > logo_height / max_height:
                        new_width = max_width
                        new_height = new_width / aspect_ratio
                    else:
                        new_height = max_height
                        new_width = new_height * aspect_ratio

                    if multiple_clip.transform and multiple_clip.transform.scale:
                        new_width = new_width * multiple_clip.transform.scale
                        new_height = new_height * multiple_clip.transform.scale

                    # Resize logo
                    logo_clip = logo_clip.resized(height=new_height, width=new_width)

                    # Calculate vertical position based on section
                    section_size = (
                        RESOLUTION[1] / 3
                    )  # Divide screen into 3 equal sections

                    if multiple_clip.position == PositionEnum.TOP:
                        y_pos = (
                            section_size / 2 - new_height / 2
                        )  # Center of first section
                    elif multiple_clip.position == PositionEnum.CENTER:
                        y_pos = (
                            section_size + section_size / 2 - new_height / 2
                        )  # Center of middle section
                    elif multiple_clip.position == PositionEnum.BOTTOM:
                        y_pos = (
                            2 * section_size + section_size / 2 - new_height / 2
                        )  # Center of last section
                    else:
                        raise ValueError(f"Invalid position: {multiple_clip.position}")
                    # Set clip properties
                    if multiple_clip.transform and multiple_clip.transform.x_offset:
                        x_pos = x_pos + multiple_clip.transform.x_offset
                    if multiple_clip.transform and multiple_clip.transform.y_offset:
                        y_pos = y_pos + multiple_clip.transform.y_offset
                    logo_clip = (
                        logo_clip.with_start(multiple_clip_start_time)
                        .with_duration(multiple_clip_duration.to_seconds(fps=fps))
                        .with_position(((RESOLUTION[0] - new_width) / 2, y_pos))
                    )
                    if vfx_array:
                        logo_clip = logo_clip.with_effects(vfx_array)
                    overlay_clips.append(logo_clip)

                except Exception as e:
                    traceback.print_exc()
                    logger.error(
                        f"Error loading logo for {multiple_clip.clip_type}: {e}"
                    )
                    continue

            elif multiple_clip.clip_type == ClipTypeEnum.TITLE:
                # Handle title clips
                title_manager = EndTitleManager(
                    end_titles=self.movie_model.config.end_titles,
                    resolution=RESOLUTION,
                    fps=fps,
                    font_manager=self.font_manager,
                )
                title_clips, _ = title_manager.generate_end_titles(
                    clip_start_time=clip_start_time,
                    edl_clip=Clip(
                        clip_number=1,
                        clip_type=ClipTypeEnum.TITLE,
                        duration=clip_duration,
                    ),
                )
                overlay_clips.extend(title_clips)

            elif multiple_clip.clip_type == ClipTypeEnum.PRESENTS:
                # Skip PRESENTS clip if agent_presents is disabled
                if not getattr(self.movie_model.config, "agent_presents", None):
                    continue
                    
                # Handle presents clips
                font_size = getattr(
                    multiple_clip,
                    "font_size",
                    settings.MovieMaker.EndTitles.Main.Font.SIZE,
                )

                presents_manager = PresentsManager(resolution=RESOLUTION, fps=fps, font_manager=self.font_manager)
                presents_clips, _ = presents_manager.generate_presents(
                    clip_start_time=clip_start_time,
                    edl_clip=Clip(
                        clip_number=1,
                        clip_type=ClipTypeEnum.PRESENTS,
                        duration=clip_duration,
                    ),
                    enable_background=False,
                    text_start_time=multiple_clip_start_time,
                    text_duration=multiple_clip_duration,
                    text_vfx_array=vfx_array,
                    text_font_size=font_size,
                    transform=multiple_clip.transform,
                )
                overlay_clips.extend(presents_clips)

        return overlay_clips

    def generate_video(self) -> tuple[list, float, list]:

        RESOLUTION = self.RESOLUTION

        try:
            used_images = []
            edl = self.edl

            clips = []
            cur_end_time = 0
            final_edl_clip = None

            for edl_clip in edl.clips:
                if edl_clip.clip_type == ClipTypeEnum.IMAGE or (
                    edl_clip.clip_type == ClipTypeEnum.TITLE
                    and not self.movie_model.config.end_titles
                ):
                    img_path = str(self.ordered_images.pop(0))

                    clip_duration = EDLUtils.duration_to_seconds(
                        duration=edl_clip.duration, fps=edl.fps
                    )

                    if (
                        edl_clip.clip_effect == ClipEffectEnum.PAN_LEFT
                        or edl_clip.clip_effect == ClipEffectEnum.PAN_RIGHT
                    ):
                        x_extend = math.ceil(
                            clip_duration
                            * edl.fps
                            * settings.MovieMaker.Image.PAN_SPEED
                        )
                        clip = Effects.gen_imageclip(
                            image_path=img_path,
                            resolution=(RESOLUTION[0] + x_extend, RESOLUTION[1]),
                        )
                    else:
                        clip = Effects.gen_imageclip(
                            image_path=img_path, resolution=self.RESOLUTION
                        )

                    clip = (
                        clip.with_start(cur_end_time)
                        .with_duration(clip_duration)
                        .with_fps(edl.fps)
                    )

                    used_images.append(img_path)

                    # Add Effects
                    if edl_clip.clip_effect == ClipEffectEnum.ZOOM_IN:
                        clip = Effects.zoom_in(clip=clip)
                    elif edl_clip.clip_effect == ClipEffectEnum.ZOOM_OUT:
                        clip = Effects.zoom_out(clip=clip)
                    elif edl_clip.clip_effect == ClipEffectEnum.PAN_LEFT:
                        clip = Effects.pan_left(
                            clip=clip, fps=self.edl.fps, resolution=RESOLUTION
                        )
                    elif edl_clip.clip_effect == ClipEffectEnum.PAN_RIGHT:
                        clip = Effects.pan_right(
                            clip=clip, fps=self.edl.fps, resolution=RESOLUTION
                        )

                    clip = Effects.apply_transition(
                        clip=clip, edl_clip=edl_clip, fps=self.edl.fps
                    )

                    # Apply opacity if specified
                    if edl_clip.opacity is not None and edl_clip.opacity != 1.0:
                        clip = clip.with_opacity(edl_clip.opacity)

                    # Append clip to final video clip
                    if (
                        edl_clip.transition_in
                        and edl_clip.transition_in.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                    # Adjust clip position accordingly
                    clip = clip.with_start(cur_end_time).with_duration(clip_duration)
                    clips.append(clip)

                    # Handle multiple clips if present
                    if edl_clip.multiple:
                        overlay_clips = self._generate_multiple_clips(
                            base_clip=clip,
                            multiple_clips=edl_clip.multiple,
                            clip_start_time=cur_end_time,
                            clip_duration=edl_clip.duration,
                            fps=edl.fps,
                        )
                        clips.extend(overlay_clips)

                    logger.debug(
                        f"CLIP : IMAGE, Start: {clip.start:.2f}s, End: {clip.end:.2f}s"
                    )
                    cur_end_time += clip.duration

                    if (
                        edl_clip.transition_out
                        and edl_clip.transition_out.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                elif (
                    edl_clip.clip_type == ClipTypeEnum.TITLE
                    and self.movie_model.config.end_titles
                ):
                    if (
                        edl_clip.transition_in
                        and edl_clip.transition_in.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                    end_title_clips, cur_end_time = EndTitleManager(
                        self.movie_model.config.end_titles,
                        resolution=self.RESOLUTION,
                        fps=edl.fps,
                        font_manager=self.font_manager,
                    ).generate_end_titles(
                        clip_start_time=cur_end_time, edl_clip=edl_clip
                    )

                    clip = end_title_clips[0]
                    logger.debug(
                        f"CLIP : TITLE, Start: {clip.start:.2f}s, End: {clip.end:.2f}s"
                    )

                    clips.extend(end_title_clips)

                    if (
                        edl_clip.transition_out
                        and edl_clip.transition_out.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                elif edl_clip.clip_type == ClipTypeEnum.PRESENTS:
                    # Skip PRESENTS clip if agent_presents is disabled
                    if not getattr(self.movie_model.config, "agent_presents", None):
                        continue
                        
                    if (
                        edl_clip.transition_in
                        and edl_clip.transition_in.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                    presents_clips, cur_end_time = PresentsManager(
                        resolution=self.RESOLUTION, fps=edl.fps, font_manager=self.font_manager
                    ).generate_presents(clip_start_time=cur_end_time, edl_clip=edl_clip)

                    clip = presents_clips[0]
                    logger.debug(
                        f"CLIP : PRESENTS, Start: {clip.start:.2f}s, End: {clip.end:.2f}s"
                    )

                    clips.extend(presents_clips)

                    if (
                        edl_clip.transition_out
                        and edl_clip.transition_out.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                elif edl_clip.clip_type == ClipTypeEnum.AGENT_LOGO:
                    if (
                        edl_clip.transition_in
                        and edl_clip.transition_in.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                    agent_logo_clips, cur_end_time = AgentLogoManager(
                        resolution=self.RESOLUTION,
                        fps=edl.fps,
                        user_id=self.movie_model.user_id,
                    ).generate_agent_logo(
                        clip_start_time=cur_end_time,
                        edl_clip=edl_clip,
                        orientation=self.movie_model.config.image_orientation,
                    )

                    clip = agent_logo_clips[0]
                    logger.debug(
                        f"CLIP : AGENT_LOGO, Start: {clip.start:.2f}s, End: {clip.end:.2f}s"
                    )

                    clips.extend(agent_logo_clips)

                    if (
                        edl_clip.transition_out
                        and edl_clip.transition_out.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                elif edl_clip.clip_type == ClipTypeEnum.BROKERAGE_LOGO:
                    if (
                        edl_clip.transition_in
                        and edl_clip.transition_in.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)
                    brokerage_logo_clips, cur_end_time = BrokerageLogoManager(
                        resolution=self.RESOLUTION,
                        fps=edl.fps,
                        user_id=self.movie_model.user_id,
                    ).generate_brokerage_logo(
                        clip_start_time=cur_end_time,
                        edl_clip=edl_clip,
                        orientation=self.movie_model.config.image_orientation,
                    )

                    clip = brokerage_logo_clips[0]
                    logger.debug(
                        f"CLIP : BROKERAGE_LOGO, Start: {clip.start:.2f}s, End: {clip.end:.2f}s"
                    )
                    clips.extend(brokerage_logo_clips)

                    if (
                        edl_clip.transition_out
                        and edl_clip.transition_out.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                elif edl_clip.clip_type == ClipTypeEnum.AGENT_NAME:
                    # Skip AGENT_NAME clip if agent_presents is disabled
                    if not getattr(self.movie_model.config, "agent_presents", None):
                        continue
                        
                    if (
                        edl_clip.transition_in
                        and edl_clip.transition_in.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

                    # Render agent name (first_name + last_name)
                    agent_name = getattr(self.movie_model, "agent_name", None)
                    if not agent_name:
                        # fallback: try config or user_id
                        agent_name = getattr(self.movie_model, "user_id", "Agent")
                    from moviepy import TextClip, ColorClip

                    clip_duration = EDLUtils.duration_to_seconds(
                        duration=edl_clip.duration, fps=edl.fps
                    )
                    RESOLUTION = self.RESOLUTION
                    background_clip = (
                        ColorClip(
                            size=RESOLUTION,
                            color=settings.MovieMaker.EndTitles.General.BG_COLOR,
                        )
                        .with_start(cur_end_time)
                        .with_duration(clip_duration)
                    )
                    background_clip = Effects.apply_transition(
                        clip=background_clip, edl_clip=edl_clip, fps=self.edl.fps
                    )
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
                    text_clip = (
                        TextClip(
                            text=agent_name.upper(),
                            font_size=settings.MovieMaker.EndTitles.Main.Font.SIZE,
                            size=(text_size_x, text_size_y),
                            font=self.font_manager.get_font_path(ClipTypeEnum.AGENT_NAME),
                            color=settings.MovieMaker.EndTitles.Main.Font.COLOR,
                            margin=settings.MovieMaker.EndTitles.Main.FONT_MARGIN,
                            method=settings.MovieMaker.EndTitles.General.METHOD,
                            text_align=settings.MovieMaker.EndTitles.General.ALIGNMENT,
                        )
                        .with_start(cur_end_time)
                        .with_duration(clip_duration)
                        .with_position((text_start_x, text_start_y))
                    )
                    text_clip = Effects.apply_transition(
                        clip=text_clip, edl_clip=edl_clip, fps=self.edl.fps
                    )
                    clips.append(background_clip)
                    clips.append(text_clip)
                    cur_end_time += clip_duration
                    if (
                        edl_clip.transition_out
                        and edl_clip.transition_out.transition_frame == True
                    ):
                        black_frame, cur_end_time = Effects.black_frame(
                            fps=self.edl.fps,
                            resolution=self.RESOLUTION,
                            start_time=cur_end_time,
                        )
                        clips.append(black_frame)

            return clips, cur_end_time, used_images

        except Exception as e:
            logger.exception(f"Encountered Exception : {e}")
            raise e
        finally:
            # Cleanup temporary font files
            try:
                self.font_manager.cleanup_temp_fonts()
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup fonts: {cleanup_error}")
