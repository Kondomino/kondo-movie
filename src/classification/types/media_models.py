from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    SCENE_CLIP = "scene_clip"
    UNKNOWN = "unknown"


class ImageMedia(BaseModel):
    uri: str
    file_size_mb: Optional[float] = None
    dimensions: Optional[tuple[int, int]] = None


class VideoMedia(BaseModel):
    uri: str
    duration: Optional[float] = None
    fps: Optional[float] = None
    resolution: Optional[tuple[int, int]] = None
    file_size_mb: Optional[float] = None
    has_audio: Optional[bool] = None


class SceneClipMedia(BaseModel):
    uri: str
    source_video_uri: str
    start_time: float
    end_time: float
    duration: float
    clip_id: str


class MediaInventory(BaseModel):
    images: List[ImageMedia] = []
    videos: List[VideoMedia] = []
    scene_clips: List[SceneClipMedia] = []
    has_images: bool = False
    has_videos: bool = False
    has_scene_clips: bool = False
    
    @property
    def total_media_count(self) -> int:
        return len(self.images) + len(self.videos) + len(self.scene_clips)
    
    @property
    def is_mixed_media(self) -> bool:
        media_types = sum([self.has_images, self.has_videos, self.has_scene_clips])
        return media_types > 1


class Keyframe(BaseModel):
    uri: str  # GCS path to extracted frame image
    timestamp: float  # Time in video
    position: int  # 0=beginning, 1=middle, 2=end
    is_hero_candidate: bool = True


class SceneClip(BaseModel):
    clip_id: str
    source_video_uri: str
    start_time: float
    end_time: float
    motion_intensity: Optional[float] = None
    audio_level: Optional[float] = None
    brightness: Optional[float] = None
    stability: Optional[float] = None
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class ImageClassification(BaseModel):
    """Reuse existing image classification structure"""
    category: str
    confidence: float
    labels: List[Dict[str, Any]] = []


class ClassifiedSceneClip(BaseModel):
    clip_id: str
    source_video_uri: str
    start_time: float
    end_time: float
    duration: float
    category: str  # Same categories as images: Exterior, Living, etc.
    hero_keyframe: Keyframe
    quality_score: float
    keyframe_classifications: List[ImageClassification]
    metadata: Dict[str, Any] = {}


class VideoBuckets(BaseModel):
    """Similar to ImageBuckets but for video clips"""
    buckets: Dict[str, List["VideoBuckets.Item"]]
    
    class Item(BaseModel):
        clip_id: str
        source_video_uri: str
        start_time: float
        end_time: float
        hero_keyframe_uri: str
        score: float
        duration: float = 0.0
        
        def __init__(self, **data):
            super().__init__(**data)
            if self.duration == 0.0:
                self.duration = self.end_time - self.start_time


class VideoIntelligenceLabel(BaseModel):
    """Label from Google Video Intelligence API"""
    description: str
    confidence: float
    start_time: float
    end_time: float


class VideoScene(BaseModel):
    """Basic video scene detected by Google Video Intelligence API"""
    scene_id: str
    start_time: float
    end_time: float
    duration: float
    video_intelligence_labels: List[VideoIntelligenceLabel] = []
    primary_label: str
    confidence_score: float


class SceneKeyframe(BaseModel):
    """Keyframe extracted from a video scene"""
    position: str = Field(..., description="Position in scene: start, middle, end")
    timestamp: float = Field(..., description="Exact timestamp in video")
    gs_url: str = Field(..., description="GCS URL of keyframe image")


class EnhancedVideoScene(BaseModel):
    """Enhanced scene with Google Video Intelligence data and keyframe analysis"""
    scene_id: str
    start_time: float
    end_time: float
    duration: float
    
    # Google Video Intelligence data
    video_intelligence_labels: List[VideoIntelligenceLabel] = []
    primary_label: str
    confidence_score: float
    
    # Keyframe data
    keyframe_timestamp: float = Field(..., description="Middle timestamp for primary keyframe")
    keyframes: List[SceneKeyframe] = Field(default_factory=list, description="All extracted keyframes")
    primary_keyframe_gs_url: str = Field(..., description="Primary keyframe GCS URL")
    
    # Google Vision API classification of primary keyframe
    vision_classification: Optional[ImageClassification] = None
    
    # Combined classification results
    final_category: str = "Unknown"
    combined_confidence: float = 0.0
    
    # Processing metadata
    extraction_metadata: Dict[str, Any] = Field(default_factory=dict)
    processed_at: Optional[datetime] = None


class EnhancedVideoBuckets(BaseModel):
    """Enhanced video buckets with Google Video Intelligence integration"""
    buckets: Dict[str, List["EnhancedVideoBuckets.Item"]]
    processing_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Item(BaseModel):
        scene_id: str
        source_video_uri: str
        start_time: float
        end_time: float
        duration: float
        
        # Enhanced data
        primary_keyframe_gs_url: str
        video_intelligence_labels: List[VideoIntelligenceLabel] = []
        vision_classification: Optional[ImageClassification] = None
        
        # Scoring
        video_intelligence_score: float = 0.0
        vision_api_score: float = 0.0
        combined_score: float = 0.0
        
        def __init__(self, **data):
            super().__init__(**data)
            if self.duration == 0.0:
                self.duration = self.end_time - self.start_time


class VideoIntelligenceResults(BaseModel):
    """Results from Google Video Intelligence API analysis"""
    video_gs_url: str
    total_scenes: int
    total_duration: float
    scenes: List[EnhancedVideoScene] = []
    processing_summary: Dict[str, Any] = Field(default_factory=dict)
    processed_at: datetime = Field(default_factory=datetime.now)


class UnifiedClassificationResults(BaseModel):
    """Results from unified classification of mixed media"""
    images: Optional[Dict[str, Any]] = None  # ImageBuckets as dict
    videos: Optional[Dict[str, Any]] = None  # VideoBuckets as dict
    enhanced_videos: Optional[VideoIntelligenceResults] = None  # Enhanced video results
    video_scene_buckets: Optional[Any] = None  # VideoSceneBuckets from consolidated classification
    mixed_media: bool = False
    unified_buckets: Optional[Dict[str, Any]] = None  # Combined buckets for mixed media
    media_inventory: Optional[MediaInventory] = None
    
    # Processing metadata
    google_video_intelligence_used: bool = False
    google_vision_api_used: bool = False
    processing_duration: Optional[float] = None
