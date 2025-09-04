"""
Scraper Engine Configuration and Management

This module handles the configuration and instantiation of property scraping engines
for different tenants. It provides a centralized way to manage engine fallback logic
and tenant-specific configurations.
"""

from typing import List, Dict, Any, Type
from logger import logger
from config.config import settings

# Import all available scrapers
from property.scrapers.daniel_gale import DanielGale
from property.scrapers.jenna_cooper_la import JennaCooperLA
from property.scrapers.coldwell_banker import ColdwellBanker
from property.scrapers.redfin_engine import RedfinEngine
from property.scrapers.corcoran import Corcoran
from property.scrapers.compass import Compass
from property.scrapers.zillow import Zillow
from property.scrapers.scraper_base import ScraperBase


class ScraperEngineManager:
    """
    Manages scraper engine configurations and provides engine lists for tenants.
    
    This class centralizes all engine configuration logic, making it easy to:
    - Add new tenants
    - Modify engine priorities
    - Update fallback strategies
    - Maintain consistent engine ordering
    """
    
    # Default fallback engines in priority order - used as base for all tenants
    DEFAULT_FALLBACK_ENGINES = [Compass, ColdwellBanker, Zillow, Corcoran]
    
    # Tenant-specific engine configurations
    TENANT_ENGINE_CONFIG = {
        'daniel_gale': {
            'primary': DanielGale, 
            'fallback_count': 4,
            'description': 'Daniel Gale tenant with DanielGale engine first'
        },
        'jenna_cooper_la': {
            'primary': JennaCooperLA, 
            'fallback_count': 4,
            'description': 'Jenna Cooper LA tenant with JennaCooperLA engine first'
        },
        'coldwell_banker': {
            'primary': ColdwellBanker, 
            'fallback_count': 3,
            'description': 'Coldwell Banker tenant with ColdwellBanker engine first'
        },
        'compass': {
            'primary': Compass, 
            'fallback_count': 3,
            'description': 'Compass tenant with Compass engine first'
        },
        'corcoran_group': {
            'primary': Corcoran, 
            'fallback_count': 3,
            'description': 'Corcoran Group tenant with Corcoran engine first'
        },
        'zillow': {
            'primary': Zillow, 
            'fallback_count': 3,
            'description': 'Zillow tenant with Zillow engine first'
        },
        'watson_salari_group': {
            'primary': Zillow, 
            'fallback_count': 3,
            'description': 'Watson Salari Group tenant (using Zillow until WatsonSalariGroup is implemented)',
            'todo': 'Replace with WatsonSalariGroup when available'
        },
    }
    
    @classmethod
    def get_engines_for_tenant(cls, tenant_id: str) -> List[ScraperBase]:
        """
        Get the list of scraper engines for a specific tenant.
        
        Args:
            tenant_id: The tenant identifier
            
        Returns:
            List of instantiated scraper engines in priority order
        """
        logger.info(f"[SCRAPER_ENGINE_MANAGER] Getting engines for tenant_id: '{tenant_id}'")
        
        # Check if web scraping is enabled
        if not settings.FeatureFlags.ENABLE_WEB_SCRAPING:
            logger.warning(f"[SCRAPER_ENGINE_MANAGER] Web scraping disabled via feature flag - returning empty engine list")
            return []
        
        # Check if tenant has specific configuration
        if tenant_id in cls.TENANT_ENGINE_CONFIG:
            config = cls.TENANT_ENGINE_CONFIG[tenant_id]
            primary_engine = config['primary']
            fallback_count = config['fallback_count']
            description = config.get('description', f'{tenant_id} tenant configuration')
            
            logger.info(f"[SCRAPER_ENGINE_MANAGER] {description}")
            logger.info(f"[SCRAPER_ENGINE_MANAGER] Primary: {primary_engine.__name__}, Fallbacks: {fallback_count}")
            
            return cls._create_engine_list(primary_engine, fallback_count)
        
        # Default engines for other tenants (including editora)
        logger.info(f"[SCRAPER_ENGINE_MANAGER] Default tenant engines for '{tenant_id}' - using default engine order")
        return cls.get_default_engines()
    
    @classmethod
    def _create_engine_list(cls, primary_engine_class: Type[ScraperBase], fallback_count: int = None) -> List[ScraperBase]:
        """
        Create a list of engines with primary engine first and fallbacks.
        
        Args:
            primary_engine_class: The primary engine class to instantiate first
            fallback_count: Maximum number of fallback engines to include
            
        Returns:
            List of instantiated scraper engines
        """
        engines = []
        
        # Add primary engine
        engines.append(primary_engine_class())
        logger.debug(f"[SCRAPER_ENGINE_MANAGER] Added primary engine: {primary_engine_class.__name__}")
        
        # Add fallback engines (excluding duplicates of primary)
        fallback_engines = [
            engine_class() for engine_class in cls.DEFAULT_FALLBACK_ENGINES 
            if engine_class != primary_engine_class
        ]
        
        # Limit fallback count if specified
        if fallback_count is not None:
            fallback_engines = fallback_engines[:fallback_count]
        
        engines.extend(fallback_engines)
        
        engine_names = [engine.__class__.__name__ for engine in engines]
        logger.info(f"[SCRAPER_ENGINE_MANAGER] Created engine list: {engine_names}")
        
        return engines
    
    @classmethod
    def get_default_engines(cls) -> List[ScraperBase]:
        """Get a fresh copy of the default engine order."""
        engines = [engine_class() for engine_class in cls.DEFAULT_FALLBACK_ENGINES]
        logger.debug(f"[SCRAPER_ENGINE_MANAGER] Created default engines: {[e.__class__.__name__ for e in engines]}")
        return engines
    
    @classmethod  
    def update_default_engine_order(cls, new_order: List[Type[ScraperBase]]):
        """
        Update the default engine order (for configuration changes).
        
        Args:
            new_order: List of engine classes in the new priority order
        """
        logger.info(f"[SCRAPER_ENGINE_MANAGER] Updating default engine order to: {[engine.__name__ for engine in new_order]}")
        cls.DEFAULT_FALLBACK_ENGINES = new_order
    
    @classmethod
    def add_tenant_config(cls, tenant_id: str, primary_engine: Type[ScraperBase], fallback_count: int = 3, description: str = None):
        """
        Add a new tenant configuration.
        
        Args:
            tenant_id: The tenant identifier
            primary_engine: The primary engine class for this tenant
            fallback_count: Number of fallback engines to include
            description: Optional description for logging
        """
        config = {
            'primary': primary_engine,
            'fallback_count': fallback_count,
            'description': description or f'{tenant_id} tenant with {primary_engine.__name__} engine first'
        }
        
        cls.TENANT_ENGINE_CONFIG[tenant_id] = config
        logger.info(f"[SCRAPER_ENGINE_MANAGER] Added tenant configuration for '{tenant_id}': {config['description']}")
    
    @classmethod
    def get_tenant_summary(cls, tenant_id: str) -> Dict[str, Any]:
        """
        Get a summary of the engine configuration for a specific tenant.
        
        Args:
            tenant_id: The tenant identifier
            
        Returns:
            Dictionary with tenant engine configuration details
        """
        engines = cls.get_engines_for_tenant(tenant_id)
        
        return {
            'tenant_id': tenant_id,
            'engines': [engine.__class__.__name__ for engine in engines],
            'engine_count': len(engines),
            'primary_engine': engines[0].__class__.__name__ if engines else None,
            'fallback_engines': [engine.__class__.__name__ for engine in engines[1:]] if len(engines) > 1 else [],
            'has_custom_config': tenant_id in cls.TENANT_ENGINE_CONFIG,
            'config': cls.TENANT_ENGINE_CONFIG.get(tenant_id, 'Using default configuration')
        }
    
    @classmethod
    def get_all_available_engines(cls) -> List[str]:
        """Get a list of all available engine names."""
        return [
            'DanielGale', 'JennaCooperLA', 'ColdwellBanker', 
            'RedfinEngine', 'Corcoran', 'Compass', 'Zillow'
        ]
    
    @classmethod
    def get_configured_tenants(cls) -> List[str]:
        """Get a list of all configured tenant IDs."""
        return list(cls.TENANT_ENGINE_CONFIG.keys())


# Convenience functions for backward compatibility and easy access
def get_engines_for_tenant(tenant_id: str) -> List[ScraperBase]:
    """Convenience function to get engines for a tenant."""
    return ScraperEngineManager.get_engines_for_tenant(tenant_id)


def get_tenant_engine_summary(tenant_id: str) -> Dict[str, Any]:
    """Convenience function to get tenant engine summary."""
    return ScraperEngineManager.get_tenant_summary(tenant_id)
