"""
Auth dependency stub.

Stytch was purged as part of handing auth ownership to kondos-api (kondo-movie
becomes stateless and trusts an upstream-validated user id). While the legacy
`Depends(authenticate)` wiring still exists in `main.py`, calling it returns
501 with a pointer to the new path: routes should be removed or proxied
through kondos-api with `X-User-Id` (or equivalent) set by the upstream.

Once main.py is rewritten to use the proxied pattern, this whole file goes.
"""

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from logger import logger
from account.account_model import UserData  # re-exported for callers that import it from here

security = HTTPBearer(auto_error=False)


async def authenticate(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserData:
    """Loud stub — kondo-movie no longer authenticates requests itself."""
    raise HTTPException(
        status_code=501,
        detail=(
            "kondo-movie no longer authenticates requests. "
            "Auth is owned by kondos-api; remove Depends(authenticate) from "
            "routes and have the upstream pass user identity in headers "
            "(e.g. X-User-Id) instead."
        ),
    )


def get_auth_dependency():
    """
    Backward-compat shim. Some callers used this to get an "auth or no-op" dep.
    Now always returns a no-op so routes that survive don't gain a hard 501.
    """
    async def _no_auth() -> None:
        return None

    return Depends(_no_auth)
