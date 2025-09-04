
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


from logger import logger
from config.config import settings
from utils.session_utils import get_session_refs_by_ids
from gcp.db import db_client
from account.stytch_manager import stytch_client
from account.account_model import *

# Token authentication dependency
security = HTTPBearer()

async def authenticate(credentials: HTTPAuthorizationCredentials = Depends(security)):
    session_token = credentials.credentials  # Extract session token from Authorization header
    
    try:
        # Authenticate session with Stytch
        user_id = stytch_client.authenticate(session_token=session_token)
        
        # Check if user_id is missing
        if not user_id:
            raise HTTPException(status_code=400, detail="Authentication Failed! User doesn't exist!")

        # Fetch user from Firestore
        user_ref, _, _ = get_session_refs_by_ids(user_id=user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            raise HTTPException(status_code=400, detail="Authentication Failed! User doesn't exist!")

        user_data = UserData.model_validate(user_doc.to_dict())

        # Validate user data
        if user_data.is_deleted:
            raise HTTPException(status_code=400, detail="User doesn't exist!")

        if user_data.id == user_id:
            return user_data  # Proceed with the request
        else:
            raise HTTPException(status_code=400, detail="Authentication Failed!")

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication Failed! {str(e)}")
