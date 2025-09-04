from typing import Optional
from config.config import settings
from account.account_model import UserData

def get_tenant_info(user_data: UserData) -> Optional[dict]:
    """
    Get tenant information for a user.
    
    Args:
        user_data: UserData object containing tenant_id
        
    Returns:
        Tenant configuration dict or None if tenant not found
    """
    # Handle case where user_data.tenant_id might be None (for backward compatibility)
    tenant_id = getattr(user_data, 'tenant_id', None) or settings.Tenants.DEFAULT_TENANT_ID
    from logger import logger
    logger.info(f"Getting tenant info for tenant_id: {tenant_id}")
    
    # Access tenant info from Pydantic model
    tenants_dict = settings.Tenants.TENANTS.model_dump()
    logger.info(f"Available tenants: {list(tenants_dict.keys())}")
    
    tenant_info = tenants_dict.get(tenant_id)
    logger.info(f"Found tenant info: {tenant_info}")
    return tenant_info

def get_tenant_name(user_data: UserData) -> str:
    """
    Get tenant name for a user.
    
    Args:
        user_data: UserData object containing tenant_id
        
    Returns:
        Tenant name or default tenant name if not found
    """
    tenant_info = get_tenant_info(user_data)
    if tenant_info:
        return tenant_info.get('name', 'Unknown')
    else:
        # Fallback to default tenant
        tenants_dict = settings.Tenants.TENANTS.model_dump()
        default_tenant = tenants_dict.get(settings.Tenants.DEFAULT_TENANT_ID, {})
        return default_tenant.get('name', 'Unknown')

def get_tenant_url(user_data: UserData) -> str:
    """
    Get tenant URL for a user.
    
    Args:
        user_data: UserData object containing tenant_id
        
    Returns:
        Tenant URL or default tenant URL if not found
    """
    tenant_info = get_tenant_info(user_data)
    if tenant_info:
        return tenant_info.get('url', '')
    else:
        # Fallback to default tenant
        tenants_dict = settings.Tenants.TENANTS.model_dump()
        default_tenant = tenants_dict.get(settings.Tenants.DEFAULT_TENANT_ID, {})
        return default_tenant.get('url', '')

def get_tenant_by_id(tenant_id: str) -> Optional[dict]:
    """
    Get tenant information by tenant ID.
    
    Args:
        tenant_id: The tenant ID to look up
        
    Returns:
        Tenant configuration dict or None if tenant not found
    """
    tenants_dict = settings.Tenants.TENANTS.model_dump()
    return tenants_dict.get(tenant_id)

def get_all_tenants() -> dict:
    """
    Get all available tenants.
    
    Returns:
        Dictionary of all tenant configurations
    """
    return settings.Tenants.TENANTS.model_dump() 