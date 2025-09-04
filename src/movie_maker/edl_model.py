from enum import Enum
import math
from typing import List, Optional, TYPE_CHECKING, Annotated, ForwardRef
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    field_serializer,
    model_validator,
    ValidationError,
    AnyUrl,
)

from utils.common_models import CaseInsensitiveEnum

if TYPE_CHECKING:
    from movie_maker.movie_model import MovieModel


class ClipEffectEnum(str, CaseInsensitiveEnum):
    ZOOM_IN = "ZoomIn"
    ZOOM_OUT = "ZoomOut"
    PAN_LEFT = "PanLeft"
    PAN_RIGHT = "PanRight"


class TransitionEffectEnum(str, CaseInsensitiveEnum):
    CUT = "Cut"
    FADE = "Fade"


class ClipTypeEnum(str, CaseInsensitiveEnum):
    IMAGE = "Image"
    TITLE = "Title"
    PRESENTS = "Presents"
    AGENT_LOGO = "AgentLogo"
    BROKERAGE_LOGO = "BrokerageLogo"
    AGENT_NAME = "AgentName"
    ADDRESS = "Address"
    PROPERTY_LOCATION = "PropertyLocation"
    OCCASION_TEXT = "OccasionText"
    OCCASION_SUBTITLE = "OccasionSubtitle"


class OrientationEnum(str, CaseInsensitiveEnum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    HYBRID = "hybrid"


class Frames(BaseModel):
    frames: int = Field(..., ge=0, description="Number of frames")


class Duration(BaseModel):
    seconds: int = Field(..., ge=0, description="Number of seconds")
    frames: int = Field(..., ge=0, description="Number of frames")

    @classmethod
    def from_seconds(cls, seconds: float, fps: int) -> "Duration":
        whole_seconds = math.floor(seconds)
        frames = int((seconds - whole_seconds) * fps)
        return cls(seconds=whole_seconds, frames=frames)

    def to_seconds(self, fps: int) -> float:
        return self.seconds + self.frames / fps


class Transition(BaseModel):
    effect: TransitionEffectEnum = Field(
        TransitionEffectEnum.CUT,
        description="Transition effect, either 'Cut' or 'Fade'",
    )
    duration: Duration = Field(..., description="Duration of the transition")
    transition_frame: Optional[bool] = Field(
        False, description="Whether to include a transition frame"
    )


class PositionEnum(str, CaseInsensitiveEnum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class Transform(BaseModel):
    scale: Optional[float] = Field(
        None, description="Scale factor for the clip (optional)"
    )
    x_offset: Optional[float] = Field(
        None, description="Horizontal offset in pixels (optional)"
    )
    y_offset: Optional[float] = Field(
        None, description="Vertical offset in pixels (optional)"
    )


class MultipleClip(BaseModel):
    clip_type: ClipTypeEnum = Field(..., description="Type of clip to overlay")
    position: PositionEnum = Field(..., description="Vertical position of the clip")
    font_size: Optional[int] = Field(
        None, description="Custom font size for text elements (optional)"
    )
    start: Optional[Duration] = Field(
        None, description="Start time of the clip (optional)"
    )
    end: Optional[Duration] = Field(None, description="End time of the clip (optional)")
    fade_in: Optional[Frames] = Field(
        None, description="Duration of the fade in effect (optional)"
    )
    fade_out: Optional[Frames] = Field(
        None, description="Duration of the fade out effect (optional)"
    )
    transform: Optional[Transform] = Field(
        None, description="Transform for the clip (optional)"
    )


class Clip(BaseModel):
    clip_number: int = Field(
        ..., ge=1, description="Monotonically increasing clip number starting at 1"
    )
    clip_type: ClipTypeEnum = Field(
        ClipTypeEnum.IMAGE, description="Type of clip - Image | Title"
    )
    duration: Duration = Field(..., description="Duration of the clip")
    clip_effect: Optional[ClipEffectEnum] = Field(
        default=None, description="Effect applied to the clip"
    )
    opacity: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Opacity of the clip (0.0 to 1.0, where 1.0 is fully opaque)",
    )
    multiple: Optional[list[MultipleClip]] = Field(
        default=None,
        max_items=10,
        description="Optional list of up to 10 clips to overlay on the image",
    )
    transition_in: Optional[Transition] = Field(
        None, description="Transition effect when the clip starts (optional)"
    )
    transition_out: Optional[Transition] = Field(
        None, description="Transition effect when the clip ends (optional)"
    )


class EDL(BaseModel):
    name: str = Field(..., description="Name of the project or global setting")
    soundtrack_uri: AnyUrl = Field(
        ..., description="URI of the corresponding soundtrack used in the video"
    )
    fps: int = Field(..., gt=0, description="Frames per second setting")
    clips: List[Clip] = Field(..., description="List of clips in the EDL")
    rank: int = Field(..., description="Rank / Priority of EDL")
    orientation: OrientationEnum = Field(
        default=OrientationEnum.LANDSCAPE,
        description="Orientation of the video (portrait, landscape, or hybrid)"
    )
    voiceover_offset: Optional[int] = Field(
        None, description="Number of seconds to offset the voiceover"
    )

    @field_serializer("soundtrack_uri")
    def serialize_anyurl(self, url: AnyUrl) -> str:
        return str(url)

    @field_validator("clips")
    def validate_clips_sequence(cls, v, values):
        if not v:
            raise ValidationError("clips list cannot be empty")
        for index, clip in enumerate(v, start=1):
            if clip.clip_number != index:
                raise ValidationError(
                    f"clip_number must be sequential starting at 1. Expected {index}, got {clip.clip_number}"
                )
        return v
    @model_validator(mode="after")
    def check_frames_within_fps(cls, values):
        fps = values.fps
        clips = values.clips
        for clip in clips:
            # Check main duration
            if clip.duration.frames >= fps:
                raise ValidationError(
                    f"Clip {clip.clip_number}: duration.frames ({clip.duration.frames}) must be less than fps ({fps})."
                )
            # Check transition_in duration if present
            if clip.transition_in and clip.transition_in.duration.frames >= fps:
                raise ValidationError(
                    f"Clip {clip.clip_number}: transition_in.duration.frames ({clip.transition_in.duration.frames}) must be less than fps ({fps})."
                )
            # Check transition_out duration if present
            if clip.transition_out and clip.transition_out.duration.frames >= fps:
                raise ValidationError(
                    f"Clip {clip.clip_number}: transition_out.duration.frames ({clip.transition_out.duration.frames}) must be less than fps ({fps})."
                )
        return values

    class Config:
        arbitrary_types_allowed = True
