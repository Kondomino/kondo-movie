"""
Unified database manager that provides a single interface for both PostgreSQL and Firestore.
This acts as a bridge between the old Firestore-based code and the new PostgreSQL implementation.
"""

import os
from typing import Optional, Any, Dict, List
from contextlib import contextmanager

from sqlalchemy import text
from logger import logger
from config.config import settings
from database.database_manager import database_manager


class UnifiedDBManager:
    """
    Unified database manager that provides compatibility between Firestore and PostgreSQL.
    Allows gradual migration from Firestore to PostgreSQL.
    """
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.provider = settings.Database.PROVIDER if hasattr(settings, 'Database') else "Firestore"
        self.postgres_enabled = settings.FeatureFlags.ENABLE_POSTGRESQL if hasattr(settings.FeatureFlags, 'ENABLE_POSTGRESQL') else False
        logger.info(f"[UNIFIED_DB_MANAGER] Initialized with provider: {self.provider}, PostgreSQL enabled: {self.postgres_enabled}")

    @contextmanager
    def get_session(self):
        """Get database session context manager for PostgreSQL"""
        if self.provider == "PostgreSQL" and self.postgres_enabled:
            session = database_manager.get_session()
            try:
                yield session
            except Exception as e:
                logger.exception(f"[UNIFIED_DB_MANAGER] Session error: {e}")
                session.rollback()
                raise
            finally:
                session.close()
        else:
            # For Firestore or when PostgreSQL is disabled, yield None
            # This allows code to check if session is None and use Firestore instead
            yield None

    def get_firestore_client(self):
        """Get Firestore client for fallback operations"""
        try:
            if self.provider == "Firestore" or not self.postgres_enabled:
                from gcp.db import db_client
                return db_client
            else:
                logger.warning("[UNIFIED_DB_MANAGER] Firestore client requested but PostgreSQL is active")
                return None
        except Exception as e:
            logger.exception(f"[UNIFIED_DB_MANAGER] Failed to get Firestore client: {e}")
            return None

    def is_postgresql_active(self) -> bool:
        """Check if PostgreSQL is the active database provider"""
        return self.provider == "PostgreSQL" and self.postgres_enabled and settings.FeatureFlags.ENABLE_DATABASE

    def is_firestore_active(self) -> bool:
        """Check if Firestore is the active database provider"""
        return self.provider == "Firestore" or not self.postgres_enabled

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on active database"""
        health_status = {
            "provider": self.provider,
            "postgresql_enabled": self.postgres_enabled,
            "database_enabled": settings.FeatureFlags.ENABLE_DATABASE,
            "status": "unknown"
        }
        
        try:
            if self.is_postgresql_active():
                # Test PostgreSQL connection
                with self.get_session() as session:
                    if session:
                        session.execute(text("SELECT 1"))
                        health_status["status"] = "healthy"
                        health_status["message"] = "PostgreSQL connection successful"
                    else:
                        health_status["status"] = "unhealthy"
                        health_status["message"] = "PostgreSQL session is None"
            
            elif self.is_firestore_active():
                # Test Firestore connection
                firestore_client = self.get_firestore_client()
                if firestore_client:
                    # Try a simple operation
                    collections = list(firestore_client.collections())
                    health_status["status"] = "healthy"
                    health_status["message"] = f"Firestore connection successful, {len(collections)} collections"
                else:
                    health_status["status"] = "unhealthy"
                    health_status["message"] = "Firestore client is None"
            
            else:
                health_status["status"] = "disabled"
                health_status["message"] = "Database is disabled"
                
        except Exception as e:
            health_status["status"] = "error"
            health_status["message"] = str(e)
            logger.exception(f"[UNIFIED_DB_MANAGER] Health check failed: {e}")
        
        return health_status


# Global unified database manager instance
unified_db_manager = UnifiedDBManager()


# Compatibility function for existing code
def get_db_client():
    """
    Compatibility function that returns the appropriate database client.
    For PostgreSQL, returns None (use unified_db_manager.get_session() instead).
    For Firestore, returns the Firestore client.
    """
    if unified_db_manager.is_postgresql_active():
        logger.warning("[UNIFIED_DB_MANAGER] get_db_client() called with PostgreSQL active - use get_session() instead")
        return None
    else:
        return unified_db_manager.get_firestore_client()


# For backward compatibility, create db_client variable
db_client = get_db_client()
