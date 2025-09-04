from typing import Optional
from config.config import settings
from logger import logger

def is_admin(user_email: Optional[str]) -> bool:
    """
    Check if user is admin with case-insensitive email comparison.
    
    Args:
        user_email: Email to check
        
    Returns:
        bool: True if user is admin, False otherwise
    """
    if not user_email:
        logger.debug("No user email provided for admin check")
        return False
        
    user_email_lower = user_email.lower().strip()
    admin_emails_lower = [email.lower().strip() for email in settings.Authentication.ADMINS]
    
    is_admin_user = user_email_lower in admin_emails_lower
    
    logger.debug(f"Admin check for '{user_email}': {'admin' if is_admin_user else 'not admin'} (case-insensitive)")
    
    return is_admin_user
