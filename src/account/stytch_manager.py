import json
from datetime import datetime
from pydantic import EmailStr

import stytch
from stytch.consumer.models.users import SearchUsersQueryOperator, SearchUsersQuery
from fastapi import HTTPException

from logger import logger
from config.config import settings
from gcp.secret import secret_mgr

class StytchManager:
    def __init__(self):        
        self.client = stytch.Client(
            project_id=settings.Authentication.STYTCH_PROJECT_ID,
            secret=secret_mgr.secret(settings.Secret.STYTCH_SECRET_KEY)
        )
        
    def authenticate(self, session_token:str)->str:
        response = self.client.sessions.authenticate(session_token=session_token)
        if not response:
            raise HTTPException(status_code=401, detail="Session token cannot be authorized!")
        
        response_dict = response.model_dump()
        user_id = response_dict["session"]["user_id"]

        return user_id
    
    def search(self, email:EmailStr)->dict:
        response = self.client.users.search(
            query=SearchUsersQuery(
                limit=1,
                operator=SearchUsersQueryOperator.OR, 
                operands=[
                    {
                        'filter_name': "email_address", 
                        'filter_value': [
                            email
                        ],
                    },
                ],
            ),
        )
        if response.results and len(response.results) > 0:
            return response.results[0].model_dump()
        else:
            logger.warning(f"Couldn't find email '{email}' in Stytch")
            return None
            
    
stytch_client = StytchManager()