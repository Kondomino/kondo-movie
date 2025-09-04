from google.cloud.firestore_v1.document import DocumentReference

from utils.session_utils import *
from project.project_backfill import *
from classification.image_classification_manager import ImageClassificationManager

class ProjectStatsManager():
    def __init__(self, project_ref: DocumentReference):
        self.project_ref = project_ref
        self.project_dict = self.project_ref.get().to_dict()
        self.version_stats = self.project_dict.get(PROJECT_VERSION_STATS_KEY, {})
        if not self.version_stats:
            raise ValueError(f"Project '{self.project_ref.id}' doesn't contain version stats")
    
    def _safe_subtract(self, container: dict, key: str, amount: int = 1):
        """
        Decrements the value of container[key] by 'amount' while ensuring it does not fall below zero.
        """
        container[key] = max(0, container.get(key, 0) - amount)
    
    def handle_movie_pending(self):
        self.version_stats[PROJECT_VERSION_STATE_STATS_KEY]['pending'] += 1
        self.version_stats[PROJECT_VERSION_ACTIVE_STATS_KEY]['active_count'] += 1
        self.project_ref.update({PROJECT_VERSION_STATS_KEY: self.version_stats})
    
    def handle_movie_success(self):
        self._safe_subtract(self.version_stats[PROJECT_VERSION_STATE_STATS_KEY], 'pending')
        self.version_stats[PROJECT_VERSION_STATE_STATS_KEY]['success'] += 1
        self.version_stats[PROJECT_VERSION_VIEWED_STATS_KEY]['unviewed_count'] += 1
        self.project_ref.update({PROJECT_VERSION_STATS_KEY: self.version_stats})
    
    def handle_movie_failure(self):
        self._safe_subtract(self.version_stats[PROJECT_VERSION_STATE_STATS_KEY], 'pending')
        self.version_stats[PROJECT_VERSION_STATE_STATS_KEY]['failure'] += 1
        self.project_ref.update({PROJECT_VERSION_STATS_KEY: self.version_stats})
    
    def handle_video_deleted(self, viewed_video:bool):
        self._safe_subtract(self.version_stats[PROJECT_VERSION_ACTIVE_STATS_KEY], 'active_count')
        self.version_stats[PROJECT_VERSION_ACTIVE_STATS_KEY]['deleted_count'] += 1
        if not viewed_video:
            self._safe_subtract(self.version_stats[PROJECT_VERSION_VIEWED_STATS_KEY], 'unviewed_count')
        self.project_ref.update({PROJECT_VERSION_STATS_KEY: self.version_stats})
        
    def handle_video_viewed(self):
        # Safely decrement unviewed count
        self._safe_subtract(self.version_stats[PROJECT_VERSION_VIEWED_STATS_KEY], 'unviewed_count')
        self.project_ref.update({PROJECT_VERSION_STATS_KEY: self.version_stats})
