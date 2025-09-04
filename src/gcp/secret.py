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
        cred = service_account.Credentials.from_service_account_file(SECRETS_SERVICE_ACCOUNT_KEY_FILE_PATH) \
            if os.path.exists(SECRETS_SERVICE_ACCOUNT_KEY_FILE_PATH) \
            else None
                
        self.client = secretmanager.SecretManagerServiceClient(credentials=cred)
        
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
        
secret_mgr = SecretManager()
        
def main():
    secret_id = 'OPENAI_API_KEY'
    print(secret_mgr.secret(secret_id=secret_id))
    
    pass

if __name__ == '__main__':
    main()