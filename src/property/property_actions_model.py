from datetime import datetime

from pydantic import BaseModel, Field, model_validator
from typing import Optional, Any, Dict, Self

from utils.common_models import ActionStatus
from property.property_model import PropertyModel
from property.address import Address

class FetchPropertyDetailsRequest(BaseModel):
    project_id: Optional[str] = None
    property_id: str
    property_address: str
    address_input_type: Optional[Address.AddressInputType] = Field(
        default=Address.AddressInputType.AutoComplete, description='Type of address to fetch'
    )
    title: Optional[str] = Field(
        default=None, description='Property title for title-based searches (e.g., "WEST HOLLYWOOD")'
    )

class FetchPropertyDetailsResponse(BaseModel):
    message: str
    property: Dict[str, Any]
    source: str = Field(..., description='Source of the property data (e.g., "cache", "zillow", "coldwell_banker", etc.)')

class FetchPropertyRequest(BaseModel):
    request_id: str = Field(
        ..., description='ID of request'
    )
    property_address: str = Field(
        ..., description='Address of the property to fetch'
    )
    address_input_type: Optional[Address.AddressInputType] = Field(
        default=Address.AddressInputType.AutoComplete, description='Type of address to fetch'
    )
    title: Optional[str] = Field(
        default=None, description='Property title for title-based searches (e.g., "WEST HOLLYWOOD")'
    )

class FetchPropertyResponse(BaseModel):
    request_id: str = Field(
        ..., description='ID of request'
    )
    result: ActionStatus = Field(
        ..., description='Result of the action'
    )
    last_updated: datetime = Field(
        ..., description='Time of last update'
    )
    property_details: Optional[PropertyModel] = Field(
        default=None, description='Property information'
    )
    source: Optional[str] = Field(
        default=None, description='Source of the property data (e.g., "cache_zillow", "zillow", etc.)'
    )
    
    @model_validator(mode='after')
    def validate_input(self) -> Self:
        if self.result == ActionStatus.State.SUCCESS and not self.property_details:
            raise ValueError(
                    f"Successful action needs property details"
                )
        return self

class PurgePropertyCacheRequest(BaseModel):
    property_id: str = Field(
        ..., description='ID of the property to purge cache for'
    )

class PurgePropertyCacheResponse(BaseModel):
    message: str
    property_id: str
    firestore_deleted: bool
    storage_deleted: bool