from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class PropertyModel(BaseModel):
    class MLSInfo(BaseModel):
        mls_id: Optional[str] = Field(default=None, description='MLS ID if the property is a residential listing')    
        list_price: Optional[str] = Field(..., description='Listing price of the property if it is for sale')
        description: Optional[str] = Field(None, description='Description of the property')
        specs: dict = Field(..., description='Property specifications')
        media_urls : Optional[list[str]] = Field(default=None, exclude=True, description='URLs of the property images')
        status: Optional[str] = Field(default=None, description='Property listing status (e.g., Active, Sold, Expired, etc.)')
        
    id: str = Field(..., description='Place ID of property')
    address: str = Field(..., description='Address of property')
    extraction_engine: str = Field(..., description='Engine to scrape property')
    extraction_time: datetime = Field(..., description='Time of extraction')
    media_storage_path: Optional[str] = Field(None, description='Storage path (Bucket/Folder) of property media')
    script: Optional[str] = Field(None, description='AI generated script for property')
    mls_info: Optional[MLSInfo] = Field(default=None, description='Listing information of a property if for sale')
    
    
    