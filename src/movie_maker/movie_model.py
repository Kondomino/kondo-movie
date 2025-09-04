from pydantic import BaseModel, Field, model_validator
from typing import Optional
from enum import Enum
from pathlib import Path

from utils.common_models import CaseInsensitiveEnum
from movie_maker.edl_model import EDL


class MovieModel(BaseModel):
    class Configuration(BaseModel):
        class Orientation(str, CaseInsensitiveEnum):
            """Possible image orientations."""
            Landscape = 'Landscape'
            Portrait = 'Portrait'
            Hybrid = 'Hybrid'

        class EndTitles(BaseModel):
            main_title: Optional[str] = Field(
                default=None, description="Main title displayed at the end of the movie."
            )
            sub_title: Optional[str] = Field(
                default=None, description="Subtitle displayed under the main title; requires 'main_title' to be set."
            )

            @model_validator(mode='after')
            def check_titles(self):
                if self.sub_title and not self.main_title:
                    raise ValueError('`main_title` must be provided if `sub_title` is present')
                return self

        class Narration(BaseModel):
            enabled: bool = Field(
                default=False, description="Include AI narration; defaults to False"
            )
            
            voice: Optional[str] = Field(
                default=None, description="Voice option for AI narration"
            )
                
            script: str = Field(
                ..., description="Script for AI narration and / or captions"
            )
            
            captions: bool = Field(
                default=False, description="Include captions in the movie; defaults to False ('No')."
            )

        class Occasion(BaseModel):
            enabled: bool = Field(
                default=False, description="Whether occasion text is enabled"
            )
            type: str = Field(
                ..., description="Type of occasion (e.g., 'just-listed', 'open-house', 'custom')"
            )
            occasion: str = Field(
                ..., description="Occasion text to display (e.g., 'JUST LISTED', 'OPEN HOUSE')"
            )
            subtitle: Optional[str] = Field(
                default=None, description="Optional subtitle for the occasion"
            )
            
        image_orientation: Orientation = Field(
            default=Orientation.Landscape, description="Orientation of images; defaults to 'Landscape'."
        )
        music: bool = Field(
            default=True, description='Music option for the movie'
        )
        narration: Optional[Narration] = Field(
            default=None, description='Model containing AI options such as narration and captions'
        )
        watermark: bool = Field(
            default=False, description="Include watermark in the movie; defaults to False ('No')."
        )
        end_titles: Optional[EndTitles] = Field(
            default=None, description="End titles containing 'main_title' and optionally 'sub_title'."
        )
        occasion: Optional[Occasion] = Field(
            default=None, description="Occasion text configuration"
        )
        agent_presents: bool = Field(
            default=True, description="Include agent '[Agent Name] Presents' title card; defaults to True"
        )
    
    edl: EDL = Field(
        ..., description="EDL for the movie"
    )
    ordered_images: list[str] = Field(
        ..., description="Ordered list of images to be used in the movie"
    )
    config: Configuration = Field(
        default_factory=Configuration, description='Configuration used to make movie. These are usually user preferences'
    )
    user_id: str = Field(
        ..., description="User ID for the movie"
    )
    agent_name: Optional[str] = Field(
        default=None, description="Agent's full name (first_name + last_name)"
    )
    
class MovieMakerResponseModel(BaseModel):
    video_file_path: Path = Field(
        ..., description='Local path of video file created'
    )
    voiceover_file_path: Optional[Path] = Field(
        default=None, description='Local path of voiceover file created'
    )
    captions_file_path: Optional[Path] = Field(
        default=None, description='Local path of captions (srt) file created'
    )
    used_images: list[str] = Field(
        ..., description='Cloud paths of used images'
    )
    
    