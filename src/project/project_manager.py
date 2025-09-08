
from logger import logger
from services.project_service import project_service
from services.classification_service import classification_storage_service
from services.session_service import unified_session_manager
from project.project_backfill import *
from classification.unified_classification_manager import UnifiedClassificationManager

class ProjectManager():
    def __init__(self, user_id:str, project_id:str):
        self.user_id = user_id
        self.project_id = project_id
        self.project_service = project_service
        self.classification_service = classification_storage_service
        self.session_manager = unified_session_manager
        
        # Maintain backward compatibility for existing code that expects project_ref
        self.user_ref, self.project_ref, _ = self.session_manager.get_session_refs_by_ids(
            user_id=user_id, project_id=project_id
        )
        
    def new_project(self, project_name:str, property_id:str=None)->dict:
        project = {
            "id": self.project_id, 
            "name": project_name,
            "property_id": property_id, 
            "excluded_images": []
        }
        
        # Use service layer for database operations
        created_project = self.project_service.create_project(self.user_id, self.project_id, project)
        
        # Backfill operations still use project_ref for compatibility with existing backfill code
        backfill_version_stats(project_ref=self.project_ref)
        backfill_media_signed_urls(user_id=self.user_id, project_ref=self.project_ref)
        
        return created_project or project
        
    def media_updated(self):
        # Check if project exists using service layer
        if not self.project_service.project_exists(self.user_id, self.project_id):
            logger.info(f"Project '{self.project_id}' doesn't exist. Creating one")
            self.new_project(
                project_name='Generating Project',
                property_id=None
            )
        else:
            # Backfill operations still use project_ref for compatibility
            backfill_media_signed_urls(user_id=self.user_id, project_ref=self.project_ref, force=True)
        
        # Use unified classification manager instead of direct image classification
        unified_classifier = UnifiedClassificationManager()
        
        # Check if classification should run based on available media
        if unified_classifier.should_run_classification(self.user_id, self.project_id):
            logger.info(f"[PROJECT_MANAGER] Running unified classification for project {self.project_id}")
            classification_results = unified_classifier.classify_project_media(self.user_id, self.project_id)
            
            # Store unified classification results using service layer
            if classification_results:
                self._store_unified_classification_results(classification_results)
        else:
            logger.info(f"[PROJECT_MANAGER] Skipping classification - no supported media found for project {self.project_id}")
    
    def _store_unified_classification_results(self, results):
        """
        Store unified classification results using database service layer
        
        Args:
            results: UnifiedClassificationResults object
        """
        try:
            classification_data = {}
            
            # Store media inventory information
            if results.media_inventory:
                classification_data["media_inventory"] = {
                    "total_files": results.media_inventory.total_media_count,
                    "image_count": len(results.media_inventory.images),
                    "video_count": len(results.media_inventory.videos),
                    "scene_clip_count": len(results.media_inventory.scene_clips),
                    "is_mixed_media": results.media_inventory.is_mixed_media,
                    "has_images": results.media_inventory.has_images,
                    "has_videos": results.media_inventory.has_videos,
                    "has_scene_clips": results.media_inventory.has_scene_clips
                }
            
            # Store classification results
            if results.images:
                classification_data["image_classification_status"] = results.images
            
            if results.videos:
                classification_data["video_classification_status"] = results.videos
            
            if results.mixed_media:
                classification_data["mixed_media"] = True
                if results.unified_buckets:
                    classification_data["unified_buckets"] = results.unified_buckets
            
            # Use classification service for database-agnostic storage
            success = self.classification_service.store_unified_classification(
                self.user_id, self.project_id, classification_data
            )
            
            if success:
                logger.info(f"[PROJECT_MANAGER] Stored unified classification results for project {self.project_id}")
            else:
                logger.error(f"[PROJECT_MANAGER] Failed to store unified classification results for project {self.project_id}")
            
        except Exception as e:
            logger.error(f"[PROJECT_MANAGER] Failed to store unified classification results: {e}")
        
    def fetch_signed_urls_for_images(self, images: list) -> list[dict]:
        # Check if the signed URLs are up to date 1st and backfill if necessary before fetching
        backfill_media_signed_urls(user_id=self.user_id, project_ref=self.project_ref)

        # Get project data using service layer
        project_data = self.project_service.get_project(self.user_id, self.project_id) or {}
        master_list = project_data.get("media_signed_urls", {}).get('media',[])
        signed_images = []
        for gs_url in images:
            # Look up the matching dict in the master list by comparing the gs_url
            matching_entry = next((entry for entry in master_list if entry.get("gs_url") == gs_url), None)
            if matching_entry:
                signed_images.append(matching_entry)
            else:
                # Generate a new signed URL on the fly if not found
                signed_url = StorageManager.generate_signed_url_from_gs_url(gs_url)
                parsed = StorageManager.parse_gs_url(gs_url)
                signed_images.append({
                    "file_name": parsed.get("file_name"),
                    "gs_url": gs_url,
                    "signed_url": signed_url
                })
        return signed_images

def main():
    images = [
        'gs://editora-v2-properties/ChIJAbrkAf-ewoARIu9aXDex4aQ/Images/image1.jpg',
        'gs://editora-v2-properties/ChIJAbrkAf-ewoARIu9aXDex4aQ/Images/image5.jpg'
    ]
    
    user_id = 'user-test-96ae80a5-2b9e-48cc-894e-6dc00b2b53cc'
    project_id = '01d41713-04ef-4869-88ea-b9670caf8e83'
    
    project_manager = ProjectManager(
        user_id=user_id,
        project_id=project_id
    )
    signed_urls = project_manager.fetch_signed_urls_for_images(images=images)
    print(signed_urls)

if __name__ == '__main__':
    from rich import print
    main()
        