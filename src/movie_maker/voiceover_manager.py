from typing import Optional
from datetime import datetime

from config.config import settings
from gcp.db import db_client
from gcp.storage import CloudPath
from logger import logger
from movie_maker.voiceover_model import ElevenLabs

class VoiceoverManager:
    """
    Manages versioned ElevenLabs voice mappings in Firestore.
    """
    def __init__(self):
        self.collection_ref = db_client.collection(settings.GCP.Firestore.VOICEOVER_COLLECTION_NAME)
    
    def save_voice_mappings(self, voice_mappings: ElevenLabs) -> None:
        """
        Save voice mappings with versioning support.
        Uses the version specified in the input model.
        If the version already exists, it will be updated.
        The original document is not modified.
        """
        try:
            # Get the version from the input model
            version = voice_mappings.version_info.version
            
            # Set version info
            voice_mappings.version_info.created_at = datetime.now()
            voice_mappings.version_info.is_active = True
            
            # Deactivate previous active version if it exists and is different from current version
            latest_active_version = self._get_latest_version()
            if latest_active_version is not None and latest_active_version != version:
                self._deactivate_version(latest_active_version)
            
            # Save the versioned document
            doc_id = ElevenLabs.get_doc_id(version)
            doc_ref = self.collection_ref.document(doc_id)
            doc_ref.set(voice_mappings.model_dump())
            
            logger.info(f"Saved voice mappings version {version}")
            
        except Exception as e:
            logger.exception(f"Failed to save voice mappings: {e}")
            raise e
    
    def get_voice_mappings(self, version: Optional[int] = None) -> Optional[ElevenLabs]:
        """
        Get voice mappings for a specific version or the latest active version.
        """
        try:
            if version is None:
                # Get the latest active version
                version = self._get_latest_version()
                if version is None:
                    # Fall back to the original document if no versioned documents exist
                    return self._get_original_mappings()
            
            doc_id = ElevenLabs.get_doc_id(version)
            doc_ref = self.collection_ref.document(doc_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                # Fall back to the original document if the requested version doesn't exist
                return self._get_original_mappings()
            
            return ElevenLabs.model_validate(doc.to_dict())
            
        except Exception as e:
            logger.exception(f"Failed to get voice mappings: {e}")
            raise e
    
    def link_audio_samples(self, voice_mappings: ElevenLabs) -> ElevenLabs:
        """
        Link audio samples to voice mappings.
        This method updates the sample_audio_uri field for each voice mapping
        to point to the corresponding audio file in cloud storage.
        """
        try:
            cloud_folder = settings.MovieMaker.Narration.Voiceover.MAPPINGS_STORAGE_DIR_PREFIX
            
            # Update each voice mapping with the correct audio sample URI
            for mapping in voice_mappings.voice_mappings:
                mapping.sample_audio_uri = CloudPath(
                    bucket_id=settings.GCP.Storage.TEMPLATES_BUCKET,
                    path=f'{cloud_folder}/{mapping.id}.wav'
                ).full_path()
            
            logger.info(f"Linked audio samples to voice mappings version {voice_mappings.version_info.version}")
            return voice_mappings
            
        except Exception as e:
            logger.exception(f"Failed to link audio samples: {e}")
            raise e
    
    def _get_original_mappings(self) -> Optional[ElevenLabs]:
        """
        Get voice mappings from the original document for backward compatibility.
        """
        try:
            doc_ref = self.collection_ref.document(ElevenLabs.DOC_ID)
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            # Create an ElevenLabs object from the original document
            data = doc.to_dict()
            # Add default version_info if it doesn't exist
            if "version_info" not in data:
                data["version_info"] = {
                    "version": 0,  # Use 0 to indicate pre-versioning
                    "created_at": datetime.now().isoformat(),
                    "is_active": True
                }
            
            return ElevenLabs.model_validate(data)
            
        except Exception as e:
            logger.exception(f"Failed to get original voice mappings: {e}")
            raise e
    
    def _get_latest_version(self) -> Optional[int]:
        """
        Get the latest version number from Firestore.
        This implementation avoids needing a composite index.
        """
        try:
            # Get all documents in the collection
            docs = self.collection_ref.stream()
            
            # Find the highest version number among active documents
            latest_version = None
            for doc in docs:
                data = doc.to_dict()
                version_info = data.get("version_info", {})
                
                # Check if this is an active version
                if version_info.get("is_active", False):
                    version = version_info.get("version", 0)
                    if latest_version is None or version > latest_version:
                        latest_version = version
            
            return latest_version
            
        except Exception as e:
            logger.exception(f"Failed to get latest version: {e}")
            raise e
    
    def _deactivate_version(self, version: int) -> None:
        """
        Deactivate a specific version of voice mappings.
        """
        try:
            doc_id = ElevenLabs.get_doc_id(version)
            doc_ref = self.collection_ref.document(doc_id)
            doc_ref.update({"version_info.is_active": False})
            logger.info(f"Deactivated voice mappings version {version}")
            
        except Exception as e:
            logger.exception(f"Failed to deactivate version {version}: {e}")
            raise e