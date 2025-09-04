import json

import jwt

from config.config import settings
from gcp.secret import secret_mgr

jwt_secret = secret_mgr.secret(settings.Secret.JWT_SECRET_KEY)
jwt_algorithm = settings.Authentication.JWT_ALGORITHM

def create_jwt(payload: dict) -> str:
    return jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)

def verify_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
    except Exception:
        return {"user": None, "project": None, "version": None}
