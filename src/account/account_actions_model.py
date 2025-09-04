from pydantic import BaseModel, Field, model_validator, EmailStr
from typing import Optional
from typing_extensions import Self
from enum import Enum
from datetime import datetime

from account.account_model import *

class SignupRequest(BaseModel):
    id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    agreed_to_terms: Optional[bool] = None
    tenant_id: Optional[str] = None
    
class SignupResponse(BaseModel):
    message: str

class FetchUserDetailsRequest(BaseModel):
    user_id: str

class FetchUserDetailsResponse(BaseModel):
    message: str
    details: dict

class UpdateUserDetailsRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    device_token: Optional[str] = None
    agreed_to_terms : Optional[bool] = None

class UpdateUserDetailsResponse(BaseModel):
    message: str

class UpdateUserTenantRequest(BaseModel):
    tenant_id: str

class UpdateUserTenantResponse(BaseModel):
    message: str
    user_data: dict

class CheckUserRequest(BaseModel):
    email: EmailStr

class CheckUserResponse(BaseModel):
    found: bool = False
    user: Optional[dict] = None

class DeleteUserRequest(BaseModel):
    user_id: str

class DeleteUserResponse(BaseModel):
    message: str

class ActivateAgentRequest(BaseModel):
    user_id: str
    portal_ready: bool

class ActivateAgentResponse(BaseModel):
    message: str
    user_id: str
    portal_ready: bool

class ListUnactivatedAgentsRequest(BaseModel):
    pass

class ListUnactivatedAgentsResponse(BaseModel):
    message: str
    agents: list

class SendPortalReadyEmailRequest(BaseModel):
    user_id: str
    portal_url: str

class SendPortalReadyEmailResponse(BaseModel):
    message: str