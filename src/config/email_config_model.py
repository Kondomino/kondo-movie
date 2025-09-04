from pydantic import BaseModel
from typing import Dict, Optional
import datetime as dt

class EmailConfigItem(BaseModel):
    enabled: bool = True

class EmailConfigs(BaseModel):
    video_completion: EmailConfigItem = EmailConfigItem(enabled=True)
    video_failure: EmailConfigItem = EmailConfigItem(enabled=True) 
    welcome_pilot: EmailConfigItem = EmailConfigItem(enabled=True)
    portal_ready: EmailConfigItem = EmailConfigItem(enabled=True)

class EmailConfigDocument(BaseModel):
    id: str = "email_notifications"
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None
    email_configs: EmailConfigs = EmailConfigs()

# API Models
class GetEmailConfigsResponse(BaseModel):
    message: str
    configs: EmailConfigs

class UpdateEmailConfigsRequest(BaseModel):
    configs: EmailConfigs

class UpdateEmailConfigsResponse(BaseModel):
    message: str
    configs: EmailConfigs
