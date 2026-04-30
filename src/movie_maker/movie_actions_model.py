import os

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from typing_extensions import Self
from enum import Enum
from datetime import datetime

from utils.common_models import ActionStatus, Session
from movie_maker.movie_model import MovieModel


def _is_narration_active() -> bool:
    # Master kill-switch for the narration pipeline. When NARRATION_ACTIVE
    # is not "true" the engine skips TTS regardless of what the caller
    # passed for description/voice_id. Defaults to off so a missing env
    # var keeps the engine cheap (no ElevenLabs spend).
    return os.getenv("NARRATION_ACTIVE", "false").strip().lower() == "true"


# ---------------------------------------------------------------------------
# v2 contract — proxied identity from kondos-api
# ---------------------------------------------------------------------------
# These models mirror the request shape produced by kondos-api's
# VideoEngineClient. The engine accepts v2 at the route boundary and
# translates to the legacy MakeMovieRequest before invoking the existing
# handler — so internal Firestore/Movie pipeline code keeps working
# unchanged while the public contract moves to proxied identity.

class MakeMovieAgent(BaseModel):
    id: int = Field(..., description="kondos-api agent id (proxied identity).")
    name: str = Field(..., description="Agent display name; used for end card.")
    logo_url: Optional[str] = Field(default=None, description="Agent brand logo URL.")


class MakeMovieKondo(BaseModel):
    id: int = Field(..., description="kondos-api kondo id (the property/condo).")
    address: str = Field(..., description="Kondo address; used for narration grounding.")
    brokerage_logo_url: Optional[str] = Field(default=None, description="Brokerage logo URL.")


class MakeMovieCapabilities(BaseModel):
    duration_max_seconds: int = Field(..., description="Max render duration enforced by engine.")
    images_max: int = Field(..., description="Max number of input images allowed.")
    captions_enabled: bool = Field(..., description="Whether captions should be burned in.")


class MakeMovieRequestV2(BaseModel):
    """
    Proxied-identity request from kondos-api. All identity (user/project)
    is supplied by the upstream service — the engine does not authenticate
    end-users directly. Authentication between services uses the
    X-Internal-Token shared secret on the route layer.
    """

    class Config:
        @staticmethod
        def schema_extra(schema, _):
            schema["additionalProperties"] = True

    job_id: str = Field(..., description="kondos-api-issued job id; used as the version_id internally.")
    agent: MakeMovieAgent
    kondo: MakeMovieKondo
    media_urls: list[str] = Field(..., description="Ordered list of input media URLs (R2/S3/https).")
    description: Optional[str] = Field(
        default=None,
        description="Brief from agent — used as narration script when narration is enabled. "
                    "Optional: kondos-api now accepts videos without a description (PR #20, "
                    "2026-04-29), and the engine drops the script entirely when "
                    "NARRATION_ACTIVE is off, so the field has no load-bearing role at request "
                    "time. Translator (v2_to_legacy_request) coerces None → empty string.",
    )
    edl_id: str = Field(..., description="EDL family: city_beat | dream_pop | sonoma in v1.")
    voice_id: Optional[str] = Field(default=None, description="ElevenLabs voice id; null = engine default.")
    music_url: Optional[str] = Field(default=None, description="Music override URL; null = EDL default.")
    webhook_url: str = Field(..., description="Lifecycle callback target on kondos-api.")
    capabilities: MakeMovieCapabilities

    @field_validator('job_id', 'edl_id', 'webhook_url', mode='after')
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field cannot be empty")
        return value

    @model_validator(mode='after')
    def _validate_media(self) -> Self:
        if not self.media_urls:
            raise ValueError("media_urls cannot be empty")
        return self


class MakeMovieRequest(BaseModel):
    class Config:
        # Customize the schema to set additionalProperties to true
        @staticmethod
        def schema_extra(schema, _):
            schema["additionalProperties"] = True
            
    request_id: Session = Field(
        ..., description='session information (user/project/version) of the request'
    )        
    image_repos : Optional[list[str]] = Field(
        default=None, description="List of source repos used to aggregate images from. \
            For E.g. [gs://Property_Bucket/PropertyID/Images/Path, gs://User_Bucket/UserID/Images/Path]"
    )
    ordered_images : Optional[list[str]] = Field(
        default=None, description="Cloud URIs of ORDERED images to be USED for the movie. \
            For E.g. [gs://Property_Bucket/PropertyID/Images/Path/Image1.jpeg, \
                gs://Property_Bucket/PropertyID/Images/Path/Image2.jpeg]"
    )
    excluded_images : Optional[list[str]] = Field(
        default=None, description="Cloud URIs of images to be EXCLUDED from the movie. \
            For E.g. [gs://Property_Bucket/PropertyID/Images/Path/Image21.jpeg, \
                gs://Property_Bucket/PropertyID/Images/Path/Image22.jpeg]"
    )
    template : str = Field(
        ..., description='EDL to make movie'
    )
    config : MovieModel.Configuration = Field(
        default_factory=MovieModel.Configuration, description='User configuration to make movie'
    )
    webhook_url : Optional[str] = Field(
        default=None,
        description='If set, kondo-movie POSTs a lifecycle payload here when the render completes. '
                    'Receiver auths via X-Internal-Token (KONDO_WEBHOOK_TOKEN env on this side, '
                    'KONDO_MOVIE_WEBHOOK_SECRET on the kondos-api side — same secret).'
    )
    agent_name : Optional[str] = Field(
        default=None,
        description='Display name for the agent presenting the video. In the v2 stateless flow this '
                    'comes straight from the request; pre-stateless flows looked it up from Firestore.'
    )

    @field_validator('template', mode='after')
    def validate_template(cls, value: str) -> str:
        if value == "":
            raise ValueError("Template cannot be an empty string")
        return value
    
    @model_validator(mode='after')
    def validate_input(self) -> Self:
        if not self.image_repos and not self.ordered_images:
            raise ValueError("Missing image source")
        return self


def v2_to_legacy_request(v2: MakeMovieRequestV2) -> 'MakeMovieRequest':
    """
    Translate the proxied-identity v2 contract into the engine's internal
    legacy MakeMovieRequest. The Session is synthesized from the upstream
    ids: user_id=str(agent.id), project_id=str(kondo.id), version_id=job_id.

    Side-effect note: this synthesizes Firestore docs under those ids when
    the legacy handler runs. That's acceptable for the v1 contract bridge —
    full statelessness is a later PR. The translation is deterministic.

    music_url is accepted by v2 but not yet routed into the engine's
    MovieModel (no per-render music override exists). It's captured for
    forward-compat once the EDL system grows that knob.
    """
    session = Session(
        user=Session.UserInfo(id=str(v2.agent.id)),
        project=Session.ProjectInfo(id=str(v2.kondo.id)),
        version=Session.VersionInfo(id=v2.job_id),
    )

    narration_enabled = _is_narration_active()
    # description may be None (kondos-api makes it optional in CreateVideoDto).
    # Coerce to empty string before handing off to the legacy MovieModel, which
    # expects a string. When narration is disabled the script is dropped anyway.
    description_text = v2.description or ""
    config = MovieModel.Configuration(
        narration=MovieModel.Configuration.Narration(
            enabled=narration_enabled,
            voice=v2.voice_id,
            script=description_text if narration_enabled else "",
            captions=v2.capabilities.captions_enabled if narration_enabled else False,
        ),
    )

    return MakeMovieRequest(
        request_id=session,
        image_repos=None,
        ordered_images=list(v2.media_urls),
        excluded_images=None,
        template=v2.edl_id,
        config=config,
        webhook_url=v2.webhook_url,
        agent_name=v2.agent.name,
    )


class Story(BaseModel):
    template : str = Field(
        ..., description='EDL used to make movie'
    )
    config : MovieModel.Configuration = Field(
        default_factory=MovieModel.Configuration, description='User configuration to make movie'
    )
    used_images : list[str] = Field(
        ..., description='Cloud URIs of images used in the movie, in the order they were stitched'
    )
    movie_path : str = Field(
        ..., description='Cloud Path of the movie'
    )

class MakeMovieResponse(BaseModel):
    class Config:
        # Customize the schema to set additionalProperties to true
        @staticmethod
        def schema_extra(schema, _):
            schema["additionalProperties"] = True
            
    request_id: Session = Field(
        ..., description='session information (user/project/version) of the request'
    )
    result: ActionStatus = Field(
        ..., description='Result of the action'
    )
    created: datetime = Field(
        ..., description='Time of creation'
    )
    last_updated: datetime = Field(
        ..., description='Time of last update'
    )
    story: Optional[Story] = Field(
        default=None, description='Relevant details include EDL, config & images used, video URL, etc.'
    )
    
    @field_validator('last_updated', mode='after')
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        return value
    
    @model_validator(mode='after')
    def validate_input(self) -> Self:
        if self.result.state == ActionStatus.State.SUCCESS and not self.story:                
            raise ValueError(
                    f"Successful action needs a story"
                )
        return self
        
class VersionSnapshot(BaseModel):
    class Time(BaseModel):
        created : Optional[datetime] = Field(
            default=None, description='time of last update'
        )
        
        updated : Optional[datetime] = Field(
            default=None, description='time of last update'
        )
        
        duration : Optional[float] = Field(
            default=None, description='Time (in seconds) taken from start to finish to generate video'
        )    
        
        @field_validator('created', 'updated', mode='after')
        def validate_timezone(cls, value: datetime) -> datetime:
            if value and value.tzinfo is None:
                raise ValueError("Datetime must be timezone-aware")
            return value
        
    request : Optional[MakeMovieRequest] = Field(
        ..., description='Request matching this response'
    )
    
    status : Optional[ActionStatus] = Field(
        default=None, description='Current state of the version'
    )
    
    time : Optional[Time] = Field(
        default=None, description='Time details of the version. Creation, update, duration, etc.'
    )
    
    story : Optional[Story] = Field(
        default=None, description='MOvie maker story'
    )
    
class PreselectForTemplateRequest(BaseModel):
    class Config:
        # Customize the schema to set additionalProperties to true
        @staticmethod
        def schema_extra(schema, _):
            schema["additionalProperties"] = True
            
    user: Session.UserInfo = Field(
        ..., description='User information for the request'
    )
    project: Session.ProjectInfo = Field(
        ..., description='Project information for the request'
    )
    template : str = Field(
        ..., description='EDL to make movie'
    )
    
class PreselectForTemplateResponse(BaseModel):
    class Config:
        # Customize the schema to set additionalProperties to true
        @staticmethod
        def schema_extra(schema, _):
            schema["additionalProperties"] = True
            
    result: ActionStatus = Field(
        ..., description='Result of the action'
    )
    template : str = Field(
        ..., description='EDL to make movie'
    )
    preselected_images: Optional[list[str]] = Field(
        default=None, description='List of selected and ordered images'
    )
    
    @model_validator(mode='after')
    def validate_input(self) -> Self:
        if self.result.state == ActionStatus.State.SUCCESS and not self.preselected_images:
            raise ValueError(
                    f"Successful action needs preselected images"
                )
        return self