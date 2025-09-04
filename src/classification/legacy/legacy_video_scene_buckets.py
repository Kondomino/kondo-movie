"""
VideoSceneBuckets: Streamlined storage model for video scene classification results
Mirrors ImageBuckets structure for consistency across media types
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class VideoSceneBuckets(BaseModel):
    """
    Streamlined video scene classification results organized by category buckets.
    Designed to mirror ImageBuckets structure for consistent frontend consumption.
    """
    
    class SceneItem(BaseModel):
        """Individual scene item within a category bucket"""
        scene_id: str = Field(..., description="Unique identifier for the scene (e.g., 'scene_30.0s')")
        source_video_uri: str = Field(..., description="GCS URI of the source video")
        start_time: float = Field(..., description="Scene start time in seconds")
        end_time: float = Field(..., description="Scene end time in seconds") 
        confidence: float = Field(..., description="Classification confidence score (0.0-1.0)")
        detection_source: str = Field(..., description="Source of classification: 'vision_api', 'video_intelligence', 'fallback'")
        keyframe_uri: Optional[str] = Field(None, description="GCS URI of extracted keyframe for this scene")
        
        @property
        def duration(self) -> float:
            """Calculate scene duration in seconds"""
            return self.end_time - self.start_time
    
    # Main buckets organized by category (mirrors ImageBuckets.buckets structure)
    buckets: Dict[str, List[SceneItem]] = Field(
        default_factory=dict, 
        description="Scenes organized by category (Kitchen, Living Room, Outdoor, etc.)"
    )
    
    # Processing metadata
    google_video_intelligence_used: bool = Field(False, description="Whether Google Video Intelligence API was used")
    google_vision_api_used: bool = Field(False, description="Whether Google Vision API was used for keyframe analysis")
    total_scenes: int = Field(0, description="Total number of scenes detected across all videos")
    processing_summary: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Summary of processing results (videos processed, keyframes extracted, etc.)"
    )
    
    def get_scenes_by_category(self, category: str) -> List[SceneItem]:
        """Get all scenes for a specific category"""
        return self.buckets.get(category, [])
    
    def get_all_scenes(self) -> List[SceneItem]:
        """Get all scenes across all categories"""
        all_scenes = []
        for scenes in self.buckets.values():
            all_scenes.extend(scenes)
        return all_scenes
    
    def get_categories(self) -> List[str]:
        """Get list of all categories with scenes"""
        return list(self.buckets.keys())
    
    def get_scene_count_by_category(self) -> Dict[str, int]:
        """Get scene count for each category"""
        return {category: len(scenes) for category, scenes in self.buckets.items()}
    
    def add_scene_to_bucket(self, category: str, scene: SceneItem):
        """Add a scene to the specified category bucket"""
        if category not in self.buckets:
            self.buckets[category] = []
        self.buckets[category].append(scene)
        self.total_scenes = sum(len(scenes) for scenes in self.buckets.values())
    
    def sort_scenes_by_confidence(self):
        """Sort scenes within each bucket by confidence (highest first)"""
        for category in self.buckets:
            self.buckets[category].sort(key=lambda scene: scene.confidence, reverse=True)
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the classification results"""
        all_scenes = self.get_all_scenes()
        
        if not all_scenes:
            return {
                "total_scenes": 0,
                "categories": 0,
                "avg_confidence": 0.0,
                "detection_sources": {}
            }
        
        # Calculate detection source distribution
        source_counts = {}
        for scene in all_scenes:
            source_counts[scene.detection_source] = source_counts.get(scene.detection_source, 0) + 1
        
        return {
            "total_scenes": len(all_scenes),
            "categories": len(self.buckets),
            "avg_confidence": sum(scene.confidence for scene in all_scenes) / len(all_scenes),
            "detection_sources": source_counts,
            "scenes_with_keyframes": len([s for s in all_scenes if s.keyframe_uri]),
            "category_distribution": self.get_scene_count_by_category()
        }
