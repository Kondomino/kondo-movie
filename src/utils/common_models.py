from pydantic import BaseModel, Field, model_validator
from typing import Optional
from typing_extensions import Self
from enum import Enum

class CaseInsensitiveEnum(Enum):
    """Enum class that enables case-insensitive matching."""
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return super()._missing_(value)


class ActionStatus(BaseModel):
    class State(str, CaseInsensitiveEnum):
        """Results of the various actions """
        PENDING = 'Pending'
        SUCCESS = 'Success'
        FAILURE = 'Failure'

    state : State = Field(
        ..., description='Result of the action'
    )
    reason : Optional[str] = Field(
        default=None, description='Reason for failure'
    )
    @model_validator(mode='after')
    def validate_input(self) -> Self:
        if self.state == ActionStatus.State.FAILURE and not self.reason:                
            raise ValueError(
                    f"Failed action needs a reason"
                )
        return self
    
    
class Session(BaseModel):
    class UserInfo(BaseModel):
        id: str = Field(
            ..., description="User ID "
        )
                
    class ProjectInfo(BaseModel):
        id: str = Field(
            ..., description="Project ID "
        )
                
    class VersionInfo(BaseModel):
        id: str = Field(
            ..., description="Version ID "
        )

    user: UserInfo
    project: ProjectInfo
    version: Optional[VersionInfo] = Field(default=None)