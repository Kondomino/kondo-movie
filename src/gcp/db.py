import os
import firebase_admin
from google.cloud import firestore
from google.oauth2 import service_account

from logger import logger
from config.config import settings

DB_SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'

class DBManager():
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.setup_db()
        return cls._instance

    def setup_db(self):
        logger.info("[GCP_DB] DBManager.setup_db() called - initializing Firestore...")
        logger.info(f"[GCP_DB] Service account file exists: {os.path.exists(DB_SERVICE_ACCOUNT_KEY_FILE_PATH)}")
        
        try:
            # Debug settings access
            try:
                logger.info(f"[GCP_DB] GCP.PROJECT_ID: {settings.GCP.PROJECT_ID}")
                logger.info(f"[GCP_DB] GCP.Firestore.DB: {settings.GCP.Firestore.DB}")
            except Exception as settings_error:
                logger.error(f"[GCP_DB] Error accessing GCP settings: {settings_error}")
                raise settings_error
            
            logger.info("[GCP_DB] Initializing Firebase Admin...")
            firebase_admin.initialize_app()
            
            cred = service_account.Credentials.from_service_account_file(DB_SERVICE_ACCOUNT_KEY_FILE_PATH) \
                if os.path.exists(DB_SERVICE_ACCOUNT_KEY_FILE_PATH) \
                else None
            
            logger.info(f"[GCP_DB] Using credentials: {'service account file' if cred else 'default credentials'}")
            
            db = settings.GCP.Firestore.DB
            logger.info(f"[GCP_DB] Creating Firestore client for project: {settings.GCP.PROJECT_ID}, database: {db}")
            self.db_client = firestore.Client(project=settings.GCP.PROJECT_ID, database=db, credentials=cred)
            logger.info("[GCP_DB] Firestore client created successfully")
        except Exception as e:
            logger.exception(f"[GCP_DB] Failed to connect to Firestore DB for project {settings.GCP.PROJECT_ID}")
            raise e

    def get_db_client(self):
        return self.db_client
    
    def delete_collection(self, collection_path: str):
        """Delete all documents in a collection"""
        try:
            collection_ref = self.db_client.collection(collection_path)
            docs = collection_ref.list_documents()
            
            deleted_count = 0
            for doc in docs:
                # Delete subcollections first
                subcollections = doc.collections()
                for subcollection in subcollections:
                    self.delete_collection(f"{collection_path}/{doc.id}/{subcollection.id}")
                
                # Delete the document
                doc.delete()
                deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} documents from collection: {collection_path}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_path}: {str(e)}")
            raise e

    def delete_document(self, document_path: str):
        """Delete a specific document"""
        try:
            doc_ref = self.db_client.document(document_path)
            doc = doc_ref.get()
            
            if not doc.exists:
                logger.warning(f"Document {document_path} does not exist")
                return 0
            
            # Delete subcollections first
            subcollections = doc_ref.collections()
            for subcollection in subcollections:
                self.delete_collection(f"{document_path}/{subcollection.id}")
            
            # Delete the document itself
            doc_ref.delete()
            logger.info(f"Deleted document: {document_path}")
            return 1
            
        except Exception as e:
            logger.error(f"Failed to delete document {document_path}: {str(e)}")
            raise e


# Lazy-loaded Firestore client with feature flag support
_db_manager_instance = None
_db_client_instance = None

def get_db_client():
    """Get Firestore client with lazy initialization and feature flag support"""
    global _db_manager_instance, _db_client_instance
    
    logger.info("[GCP_DB] get_db_client() called - checking feature flags...")
    
    # Debug current settings
    try:
        logger.info(f"[GCP_DB] ENABLE_DATABASE: {settings.FeatureFlags.ENABLE_DATABASE}")
        logger.info(f"[GCP_DB] Database.PROVIDER: {settings.Database.PROVIDER}")
        logger.info(f"[GCP_DB] ENABLE_POSTGRESQL: {settings.FeatureFlags.ENABLE_POSTGRESQL}")
    except Exception as e:
        logger.error(f"[GCP_DB] Error reading settings: {e}")
        logger.error("[GCP_DB] This suggests settings may not be initialized yet")
    
    # Check feature flags first
    try:
        if not settings.FeatureFlags.ENABLE_DATABASE:
            logger.warning("[GCP_DB] Database disabled via feature flag - returning None")
            return None
    except Exception as e:
        logger.error(f"[GCP_DB] Error checking ENABLE_DATABASE: {e}")
    
    try:
        if settings.Database.PROVIDER == "PostgreSQL" and settings.FeatureFlags.ENABLE_POSTGRESQL:
            logger.warning("[GCP_DB] PostgreSQL is active - Firestore client should not be used - returning None")
            return None
    except Exception as e:
        logger.error(f"[GCP_DB] Error checking PostgreSQL settings: {e}")
    
    # If we get here, we need to initialize Firestore
    logger.info("[GCP_DB] Feature flags allow Firestore - proceeding with initialization")
    
    # Lazy initialization only if needed
    if _db_client_instance is None:
        try:
            logger.info("[GCP_DB] Initializing DBManager...")
            _db_manager_instance = DBManager()
            _db_client_instance = _db_manager_instance.get_db_client()
            logger.info("[GCP_DB] Firestore client initialized successfully")
        except Exception as e:
            logger.exception(f"[GCP_DB] Failed to initialize Firestore client: {e}")
            return None
    else:
        logger.info("[GCP_DB] Using existing Firestore client instance")
    
    return _db_client_instance

# Create a property-like object for backward compatibility
class LazyDBClient:
    """Lazy database client that respects feature flags"""
    
    def __getattr__(self, name):
        """Delegate attribute access to the actual client"""
        logger.info(f"[GCP_DB] LazyDBClient.__getattr__() called for attribute: {name}")
        client = get_db_client()
        if client is None:
            logger.error(f"[GCP_DB] Firestore client is not available for attribute '{name}' (disabled by feature flags or using PostgreSQL)")
            raise RuntimeError("Firestore client is not available (disabled by feature flags or using PostgreSQL)")
        return getattr(client, name)
    
    def __call__(self, *args, **kwargs):
        """Make it callable if needed"""
        logger.info("[GCP_DB] LazyDBClient.__call__() called")
        client = get_db_client()
        if client is None:
            logger.error("[GCP_DB] Firestore client is not available for call (disabled by feature flags or using PostgreSQL)")
            raise RuntimeError("Firestore client is not available (disabled by feature flags or using PostgreSQL)")
        return client(*args, **kwargs)
    
    def __bool__(self):
        """Allow truthiness checks"""
        logger.info("[GCP_DB] LazyDBClient.__bool__() called")
        result = get_db_client() is not None
        logger.info(f"[GCP_DB] LazyDBClient.__bool__() returning: {result}")
        return result

# Backward compatibility: db_client behaves like the original but respects feature flags
db_client = LazyDBClient()