import os
from google.cloud import secretmanager
from google.oauth2 import service_account
from google.api_core.exceptions import NotFound

from config.config import settings
from logger import logger

SECRETS_SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-561a04f0decd.json'

class SecretManager():
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.init()
        return cls._instance
    
    def init(self):
        logger.info("[SECRET_MANAGER] Initializing Google Cloud Secret Manager...")
        cred = service_account.Credentials.from_service_account_file(SECRETS_SERVICE_ACCOUNT_KEY_FILE_PATH) \
            if os.path.exists(SECRETS_SERVICE_ACCOUNT_KEY_FILE_PATH) \
            else None
                
        self.client = secretmanager.SecretManagerServiceClient(credentials=cred)
        logger.info("[SECRET_MANAGER] Google Cloud Secret Manager initialized successfully")
        
    def secret(self, secret_id, version_id="latest"):
        """
        Accesses the payload of the specified secret version.

        Args:
            secret_id (str): The ID of the secret.
            version_id (str): The version of the secret (default: "latest").

        Returns:
            str: The secret payload as a string.
        """
        # Create the Secret Manager client
        client = self.client

        project_id = settings.GCP.PROJECT_ID
        # Build the resource name of the secret version
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"

        try:
            # Access the secret version
            response = client.access_secret_version(request={"name": name})

            # The secret payload is in bytes; decode it to a string
            payload = response.payload.data.decode("UTF-8")

            return payload

        except NotFound:
            logger.error(f"Secret {secret_id} with version {version_id} not found.")
            return None
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return None


# Lazy-loaded Secret Manager with feature flag support
_secret_manager_instance = None

def get_secret_manager():
    """Get Secret Manager with lazy initialization and feature flag support"""
    global _secret_manager_instance
    
    logger.info("[SECRET_MANAGER] get_secret_manager() called - checking feature flags...")
    
    # Check if email services are enabled (main use case for secrets)
    if not settings.FeatureFlags.ENABLE_EMAIL_SERVICES:
        logger.warning("[SECRET_MANAGER] Email services disabled - Secret Manager not available")
        return None
    
    # Lazy initialization only if needed
    if _secret_manager_instance is None:
        try:
            logger.info("[SECRET_MANAGER] Initializing SecretManager...")
            _secret_manager_instance = SecretManager()
            logger.info("[SECRET_MANAGER] SecretManager initialized successfully")
        except Exception as e:
            logger.exception(f"[SECRET_MANAGER] Failed to initialize SecretManager: {e}")
            return None
    else:
        logger.info("[SECRET_MANAGER] Using existing SecretManager instance")
    
    return _secret_manager_instance


class LazySecretManager:
    """Lazy Secret Manager that respects feature flags"""
    
    def secret(self, secret_id, version_id="latest"):
        """Get secret with feature flag checks and environment variable fallback"""
        logger.info(f"[SECRET_MANAGER] LazySecretManager.secret() called for: {secret_id}")
        
        # First check if email services are enabled
        if not settings.FeatureFlags.ENABLE_EMAIL_SERVICES:
            logger.warning(f"[SECRET_MANAGER] Email services disabled - falling back to environment variable for: {secret_id}")
            # Fallback to environment variable
            env_value = os.getenv(secret_id)
            if env_value:
                logger.info(f"[SECRET_MANAGER] Found environment variable for: {secret_id}")
                return env_value
            else:
                logger.warning(f"[SECRET_MANAGER] No environment variable found for: {secret_id}")
                return None
        
        # Get the real secret manager
        manager = get_secret_manager()
        if manager is None:
            logger.error(f"[SECRET_MANAGER] Secret Manager not available for: {secret_id}")
            # Fallback to environment variable
            env_value = os.getenv(secret_id)
            if env_value:
                logger.info(f"[SECRET_MANAGER] Falling back to environment variable for: {secret_id}")
                return env_value
            return None
        
        return manager.secret(secret_id, version_id)
    
    def __getattr__(self, name):
        """Delegate other attribute access to the real manager"""
        logger.info(f"[SECRET_MANAGER] LazySecretManager.__getattr__() called for attribute: {name}")
        
        if not settings.FeatureFlags.ENABLE_EMAIL_SERVICES:
            logger.error(f"[SECRET_MANAGER] Secret Manager not available for attribute '{name}' (email services disabled)")
            raise RuntimeError("Secret Manager is not available (email services disabled by feature flags)")
        
        manager = get_secret_manager()
        if manager is None:
            logger.error(f"[SECRET_MANAGER] Secret Manager not available for attribute '{name}'")
            raise RuntimeError("Secret Manager is not available (failed to initialize)")
        
        return getattr(manager, name)

# Backward compatibility: secret_mgr behaves like the original but respects feature flags
secret_mgr = LazySecretManager()
        
def main():
    secret_id = 'OPENAI_API_KEY'
    print(secret_mgr.secret(secret_id=secret_id))
    
    pass

if __name__ == '__main__':
    main()