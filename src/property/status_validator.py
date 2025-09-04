import json
import os
from pathlib import Path
from typing import Optional
from logger import logger

class PropertyStatusValidator:
    """
    Utility class to validate property status based on platform-specific status configurations.
    """
    
    def __init__(self):
        self.status_config = self._load_status_config()
    
    def _load_status_config(self) -> dict:
        """Load the platform status configuration from JSON file"""
        try:
            config_path = Path(__file__).parent / "scrapers" / "config" / "platforms.statuses.json"
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[STATUS_VALIDATOR] Failed to load status configuration: {str(e)}")
            return {}
    
    def is_property_inactive(self, status: Optional[str], platform: str) -> bool:
        """
        Check if a property status is considered inactive for a given platform.
        Case-insensitive comparison is performed.
        
        Args:
            status: The property status to check
            platform: The platform name (e.g., 'Compass', 'Corcoran', etc.)
            
        Returns:
            bool: True if the property is inactive, False otherwise
        """
        if not status or not platform:
            return False
            
        platform_config = self.status_config.get(platform)
        if not platform_config:
            logger.warning(f"[STATUS_VALIDATOR] No status configuration found for platform: {platform}")
            return False
        
        inactive_statuses = platform_config.get("Inactive", [])
        # Perform case-insensitive comparison
        status_lower = status.lower()
        inactive_statuses_lower = [s.lower() for s in inactive_statuses]
        is_inactive = status_lower in inactive_statuses_lower
        
        logger.info(f"[STATUS_VALIDATOR] Status '{status}' for platform '{platform}' is {'inactive' if is_inactive else 'active'} (case-insensitive match)")
        return is_inactive
    
    def get_platform_statuses(self, platform: str) -> dict:
        """
        Get all status configurations for a specific platform.
        
        Args:
            platform: The platform name
            
        Returns:
            dict: Dictionary containing 'Active' and 'Inactive' status lists
        """
        return self.status_config.get(platform, {})
    
    def get_all_platforms(self) -> list:
        """Get list of all configured platforms"""
        return list(self.status_config.keys())


# Create a singleton instance for easy import
status_validator = PropertyStatusValidator()
