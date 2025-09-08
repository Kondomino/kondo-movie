import os
from typing import Optional, Any
from sqlalchemy import create_engine, Engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from logger import logger
from config.config import settings


class DatabaseManager:
    """Environment-aware database manager supporting Firestore and PostgreSQL"""
    
    _instance = None
    _engine: Optional[Engine] = None
    _session_factory: Optional[sessionmaker] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.setup()
        return cls._instance

    def setup(self):
        """Initialize database connection based on configuration"""
        try:
            if not settings.FeatureFlags.ENABLE_DATABASE:
                logger.warning("[DATABASE_MANAGER] Database disabled via feature flag")
                return
                
            self.provider = settings.Database.PROVIDER
            self.environment = os.getenv('ENVIRONMENT', 'dev')
            
            logger.info(f"[DATABASE_MANAGER] Initializing {self.provider} database for {self.environment} environment")
            
            if self.provider == "PostgreSQL" and settings.FeatureFlags.ENABLE_POSTGRESQL:
                self._setup_postgresql()
            elif self.provider == "Firestore":
                self._setup_firestore()
            else:
                logger.warning(f"[DATABASE_MANAGER] Unknown provider '{self.provider}' or PostgreSQL disabled - using mock connection")
                
        except Exception as e:
            logger.exception(f"[DATABASE_MANAGER] Failed to initialize database: {e}")
            raise e

    def _setup_postgresql(self):
        """Setup PostgreSQL connection with environment-aware configuration"""
        try:
            database_url = self._get_database_url()
            logger.info(f"[DATABASE_MANAGER] Connecting to PostgreSQL ({self.environment})")
            
            # Create SQLAlchemy engine with connection pooling
            self._engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False  # Set to True for SQL debugging
            )
            
            # Create session factory
            self._session_factory = sessionmaker(
                bind=self._engine,
                autocommit=False,
                autoflush=False
            )
            
            # Test connection
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("[DATABASE_MANAGER] PostgreSQL connection established successfully")
                
        except Exception as e:
            logger.exception(f"[DATABASE_MANAGER] Failed to setup PostgreSQL: {e}")
            raise e

    def _get_database_url(self) -> str:
        """Get database URL based on environment"""
        if self.environment == 'prod':
            # Production: Use configuration values from settings
            try:
                # First try to use the complete DATABASE_URL if available
                if hasattr(settings.PostgreSQL.PROD, 'DATABASE_URL') and settings.PostgreSQL.PROD.DATABASE_URL:
                    database_url = settings.PostgreSQL.PROD.DATABASE_URL
                    logger.info(f"[DATABASE_MANAGER] Using DATABASE_URL from config for production")
                    return database_url
                
                # Fallback to individual configuration values
                hostname = settings.PostgreSQL.PROD.HOSTNAME
                port = settings.PostgreSQL.PROD.PORT
                username = settings.PostgreSQL.PROD.USER
                password = settings.PostgreSQL.PROD.PASSWORD
                database = settings.PostgreSQL.PROD.DATABASE
                
                ssl_mode = "require" if settings.PostgreSQL.PROD.SSL_REQUIRED else "disable"
                
                # Debug logging for production credentials
                logger.info(f"[DATABASE_MANAGER] Production configuration from settings:")
                logger.info(f"[DATABASE_MANAGER]   HOSTNAME: {'***' if hostname else 'NOT SET'}")
                logger.info(f"[DATABASE_MANAGER]   PORT: {port}")
                logger.info(f"[DATABASE_MANAGER]   USER: {'***' if username else 'NOT SET'}")
                logger.info(f"[DATABASE_MANAGER]   PASSWORD: {'***' if password else 'NOT SET'}")
                logger.info(f"[DATABASE_MANAGER]   DATABASE: {database}")
                logger.info(f"[DATABASE_MANAGER]   SSL_REQUIRED: {settings.PostgreSQL.PROD.SSL_REQUIRED} (ssl_mode: {ssl_mode})")
                
                if not all([hostname, username, password, database]):
                    logger.error(f"[DATABASE_MANAGER] Missing production database configuration:")
                    logger.error(f"[DATABASE_MANAGER]   HOSTNAME: {'✓' if hostname else '✗'}")
                    logger.error(f"[DATABASE_MANAGER]   USER: {'✓' if username else '✗'}")
                    logger.error(f"[DATABASE_MANAGER]   PASSWORD: {'✓' if password else '✗'}")
                    logger.error(f"[DATABASE_MANAGER]   DATABASE: {'✓' if database else '✗'}")
                    raise ValueError("Missing required production database configuration")
                
                database_url = f"postgresql://{username}:{password}@{hostname}:{port}/{database}?sslmode={ssl_mode}"
                logger.info(f"[DATABASE_MANAGER] Database URL: postgresql://{username}:***@{hostname}:{port}/{database}?sslmode={ssl_mode}")
                
                return database_url
                
            except AttributeError as e:
                logger.error(f"[DATABASE_MANAGER] Production database configuration missing: {e}")
                raise ValueError("Production database configuration is incomplete")
        
        else:
            # Development: Use configuration values from settings
            try:
                host = settings.PostgreSQL.DEV.HOST
                port = settings.PostgreSQL.DEV.PORT
                username = settings.PostgreSQL.DEV.USER
                password = settings.PostgreSQL.DEV.PASSWORD
                database = settings.PostgreSQL.DEV.DATABASE
                
                ssl_mode = "disable" if not settings.PostgreSQL.DEV.SSL_REQUIRED else "require"
                
                # Debug logging for credentials
                logger.info(f"[DATABASE_MANAGER] Development configuration from settings:")
                logger.info(f"[DATABASE_MANAGER]   HOST: {host}")
                logger.info(f"[DATABASE_MANAGER]   PORT: {port}")
                logger.info(f"[DATABASE_MANAGER]   USER: {username}")
                logger.info(f"[DATABASE_MANAGER]   PASSWORD: {'***' if password else 'NOT SET'}")
                logger.info(f"[DATABASE_MANAGER]   DATABASE: {database}")
                logger.info(f"[DATABASE_MANAGER]   SSL_REQUIRED: {settings.PostgreSQL.DEV.SSL_REQUIRED} (ssl_mode: {ssl_mode})")
                
                database_url = f"postgresql://{username}:{password}@{host}:{port}/{database}?sslmode={ssl_mode}"
                logger.info(f"[DATABASE_MANAGER] Database URL: postgresql://{username}:***@{host}:{port}/{database}?sslmode={ssl_mode}")
                
                return database_url
                
            except AttributeError as e:
                logger.error(f"[DATABASE_MANAGER] Development database configuration missing: {e}")
                raise ValueError("Development database configuration is incomplete")

    def _setup_firestore(self):
        """Setup Firestore connection (fallback)"""
        try:
            logger.info("[DATABASE_MANAGER] Setting up Firestore connection")
            # Import and setup existing Firestore manager
            from gcp.db import DBManager as FirestoreManager
            self._firestore_manager = FirestoreManager()
            logger.info("[DATABASE_MANAGER] Firestore connection established")
        except Exception as e:
            logger.exception(f"[DATABASE_MANAGER] Failed to setup Firestore: {e}")
            raise e

    def get_session(self) -> Session:
        """Get database session for PostgreSQL"""
        if not settings.FeatureFlags.ENABLE_DATABASE:
            raise RuntimeError("Database is disabled via feature flag")
            
        if self.provider == "PostgreSQL" and self._session_factory:
            return self._session_factory()
        else:
            raise RuntimeError(f"Session not available for provider: {self.provider}")

    def get_engine(self) -> Engine:
        """Get SQLAlchemy engine for PostgreSQL"""
        if not settings.FeatureFlags.ENABLE_DATABASE:
            raise RuntimeError("Database is disabled via feature flag")
            
        if self.provider == "PostgreSQL" and self._engine:
            return self._engine
        else:
            raise RuntimeError(f"Engine not available for provider: {self.provider}")

    def get_firestore_client(self):
        """Get Firestore client (fallback)"""
        if not settings.FeatureFlags.ENABLE_DATABASE:
            raise RuntimeError("Database is disabled via feature flag")
            
        if self.provider == "Firestore" and hasattr(self, '_firestore_manager'):
            return self._firestore_manager.get_db_client()
        else:
            raise RuntimeError("Firestore client not available")

    def close(self):
        """Close database connections"""
        if self._engine:
            self._engine.dispose()
            logger.info("[DATABASE_MANAGER] PostgreSQL connections closed")


class MockDatabaseManager:
    """Mock database manager for when database is disabled"""
    
    def get_session(self):
        logger.warning("[MOCK_DATABASE] Mock session requested - database is disabled")
        return None
        
    def get_engine(self):
        logger.warning("[MOCK_DATABASE] Mock engine requested - database is disabled")
        return None
        
    def get_firestore_client(self):
        logger.warning("[MOCK_DATABASE] Mock Firestore client requested - database is disabled")
        return None
        
    def close(self):
        logger.info("[MOCK_DATABASE] Mock database connections closed")


# Create database manager instance
def get_database_manager():
    """Get database manager instance with feature flag support"""
    if settings.FeatureFlags.ENABLE_DATABASE:
        return DatabaseManager()
    else:
        logger.warning("[DATABASE] Database disabled via feature flag - using mock manager")
        return MockDatabaseManager()


# Global database manager instance
database_manager = get_database_manager()
