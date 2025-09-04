from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from typing_extensions import Self
from enum import Enum
from datetime import datetime

from utils.common_models import ActionStatus, Session
from movie_maker.movie_model import MovieModel
    
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