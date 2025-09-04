import datetime as dt
from zoneinfo import ZoneInfo
from typing import Optional

from logger import logger
from config.config import settings
from config.email_config_model import EmailConfigDocument, EmailConfigs, EmailConfigItem
from gcp.db import db_client

class EmailConfigManager:
    """
    Singleton manager for email configuration settings.
    Handles reading and writing email configs from/to Firestore.
    """
    _instance = None
    _initialized = False
    _cached_config: Optional[EmailConfigDocument] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmailConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.collection_name = "app_configs"
            self.document_id = "email_notifications"
            self._initialized = True

    def _get_doc_ref(self):
        """Get Firestore document reference for email configs"""
        return db_client.collection(self.collection_name).document(self.document_id)

    def get_configs(self) -> EmailConfigs:
        """
        Get current email configurations from Firestore.
        Returns default configs if document doesn't exist.
        """
        try:
            doc_ref = self._get_doc_ref()
            doc = doc_ref.get()
            
            if doc.exists:
                config_doc = EmailConfigDocument.model_validate(doc.to_dict())
                self._cached_config = config_doc
                logger.debug(f"[EMAIL_CONFIG] Loaded configs from Firestore")
                return config_doc.email_configs
            else:
                # Document doesn't exist, create with defaults
                logger.info(f"[EMAIL_CONFIG] No config document found, creating with defaults")
                default_config = EmailConfigDocument()
                self._create_default_config(default_config)
                return default_config.email_configs
                
        except Exception as e:
            logger.error(f"[EMAIL_CONFIG] Failed to load configs: {str(e)}")
            # Return safe defaults if anything fails
            return EmailConfigs()

    def update_configs(self, new_configs: EmailConfigs) -> EmailConfigs:
        """
        Update email configurations in Firestore.
        """
        try:
            doc_ref = self._get_doc_ref()
            current_time = dt.datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
            
            # Check if document exists
            doc = doc_ref.get()
            if doc.exists:
                # Update existing document
                config_doc = EmailConfigDocument.model_validate(doc.to_dict())
                config_doc.email_configs = new_configs
                config_doc.updated_at = current_time
            else:
                # Create new document
                config_doc = EmailConfigDocument(
                    email_configs=new_configs,
                    created_at=current_time,
                    updated_at=current_time
                )
            
            # Save to Firestore
            doc_ref.set(config_doc.model_dump())
            self._cached_config = config_doc
            
            logger.info(f"[EMAIL_CONFIG] Updated email configurations successfully")
            return config_doc.email_configs
            
        except Exception as e:
            logger.error(f"[EMAIL_CONFIG] Failed to update configs: {str(e)}")
            raise Exception(f"Failed to update email configurations: {str(e)}")

    def _create_default_config(self, config_doc: EmailConfigDocument):
        """Create default configuration document in Firestore"""
        try:
            current_time = dt.datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
            config_doc.created_at = current_time
            config_doc.updated_at = current_time
            
            doc_ref = self._get_doc_ref()
            doc_ref.set(config_doc.model_dump())
            
            logger.info(f"[EMAIL_CONFIG] Created default email configuration document")
            
        except Exception as e:
            logger.error(f"[EMAIL_CONFIG] Failed to create default config: {str(e)}")

    def is_email_enabled(self, email_type: str) -> bool:
        """
        Check if a specific email type is enabled.
        
        Args:
            email_type: One of 'video_completion', 'video_failure', 'welcome_pilot', 'portal_ready'
            
        Returns:
            bool: True if email is enabled, False otherwise
        """
        try:
            configs = self.get_configs()
            
            if email_type == "video_completion":
                return configs.video_completion.enabled
            elif email_type == "video_failure":
                return configs.video_failure.enabled
            elif email_type == "welcome_pilot":
                return configs.welcome_pilot.enabled
            elif email_type == "portal_ready":
                return configs.portal_ready.enabled
            else:
                logger.warning(f"[EMAIL_CONFIG] Unknown email type: {email_type}")
                return True  # Default to enabled for unknown types
                
        except Exception as e:
            logger.error(f"[EMAIL_CONFIG] Error checking email config for {email_type}: {str(e)}")
            return True  # Default to enabled if error occurs

# Singleton instance
email_config_manager = EmailConfigManager()
