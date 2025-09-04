
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


from logger import logger
from config.config import settings
from utils.session_utils import get_session_refs_by_ids
from gcp.db import db_client
from account.account_model import *

# Token authentication dependency
security = HTTPBearer()

# Initialize stytch_client conditionally
stytch_client = None
if settings.FeatureFlags.ENABLE_AUTHENTICATION:
    from account.stytch_manager import stytch_client as _stytch_client
    stytch_client = _stytch_client
else:
    logger.warning("Authentication disabled via feature flag - API running in public mode")

async def authenticate(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Authentication dependency that respects the ENABLE_AUTHENTICATION feature flag.
    When authentication is disabled, this function is bypassed entirely.
    """
    if not settings.FeatureFlags.ENABLE_AUTHENTICATION:
        # This should not be called when authentication is disabled
        raise HTTPException(status_code=500, detail="Authentication called when disabled")
    
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

def get_auth_dependency() -> Optional[UserData]:
    """
    Returns the appropriate authentication dependency based on feature flags.
    When authentication is disabled, returns a function that returns None.
    When authentication is enabled, returns the authenticate function.
    """
    if settings.FeatureFlags.ENABLE_AUTHENTICATION:
        return Depends(authenticate)
    else:
        # Return a dependency that always returns None (public mode)
        async def public_mode():
            return None
        return Depends(public_mode)
