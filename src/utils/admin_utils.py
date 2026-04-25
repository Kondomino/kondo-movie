"""
Deprecated admin check.

The YAML-driven admin list was a holdover from Editora. In the Kondomino
architecture, admin status lives on the kondos-api Postgres `users.is_admin`
column and is signed into the JWT. kondo-movie does not own user identity
and should not maintain its own admin list.

Until the routes that depend on this helper are removed or rewired to trust
upstream (kondos-api proxies the request with an admin claim), `is_admin`
returns `False` deterministically — fail-closed. Any in-route check of the
form `if not is_admin(...): raise 403` will keep the route inaccessible,
which is the correct behavior post-Stytch-purge anyway.

Future: delete this helper once main.py is fully reworked.
"""

from typing import Optional

from logger import logger


def is_admin(user_email: Optional[str]) -> bool:
    """
    Always returns False.

    Admin status is owned by kondos-api (`users.is_admin` column + JWT claim).
    Callers that need it should query kondos-api or read it from the proxied
    identity headers/JWT, not call into kondo-movie.
    """
    logger.warning(
        "[admin_utils.is_admin] called for '%s' — kondo-movie no longer "
        "maintains an admin list; returning False. Admin status lives on "
        "kondos-api.",
        user_email,
    )
    return False
