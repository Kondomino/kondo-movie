from pydantic import BaseModel
from typing import List, Optional, Any, Dict
import datetime as dt

# POST endpoint models (as previously defined)

class NewMediaUploadedRequest(BaseModel):
    project_id: str

class NewMediaUploadedResponse(BaseModel):
    message: str

class VideoSceneDisplay(BaseModel):
    scene_id: int
    start_time: float
    end_time: float
    duration: float
    scene_type: str
    scene_category: str
    primary_label: str
    confidence: float
    emoji: str  # 🏠 for indoor, 🌳 for outdoor, etc.
    display_name: str  # "Living Room", "Kitchen", etc.

class FetchVideoScenesResponse(BaseModel):
    message: str
    video_uri: str
    total_scenes: int
    scenes: List[VideoSceneDisplay]
    video_duration: float

class DeleteMediaFilesRequest(BaseModel):
    project_id: str
    gs_urls: list[str]

class DeleteMediaFilesResponse(BaseModel):
    message: str

class CreateVideoRequest(BaseModel):
    project_id: str
    name: Optional[str] = ""
    property_id: Optional[str] = None
    orientation: Optional[str] = "Landscape"
    included_endtitle: Optional[bool] = False
    end_title: Optional[str] = ""
    end_subtitle: Optional[str] = ""
    included_music: Optional[bool] = True
    selected_music: Optional[str] = ""
    included_ai_narration: Optional[bool] = True
    selected_ai_narration: Optional[str] = ""
    included_captions: Optional[bool] = False
    selected_ai_voice: Optional[str] = ""
    version_id: Optional[str] = None
    ordered_images: Optional[List[str]] = None
    included_occasion_text: Optional[bool] = False
    selected_occasion: Optional[str] = ""
    occasion_subtitle: Optional[str] = ""
    custom_occasion_text: Optional[str] = ""
    included_agent_presents: Optional[bool] = True

class CreateVideoResponse(BaseModel):
    message: str
    project_id: str
    version_id: str

class FetchProjectImagesRequest(BaseModel):
    project_id: str

class FetchProjectImagesResponse(BaseModel):
    message: str
    images: List[Dict[str, Any]]
    signature_expiry: Optional[dt.datetime] = None

class FetchProjectVideosRequest(BaseModel):
    project_id: str

class FetchProjectVideosResponse(BaseModel):
    message: str
    videos: List[Dict[str, Any]]
    signature_expiry: Optional[dt.datetime] = None

class FetchProjectMediaRequest(BaseModel):
    project_id: str

class FetchProjectMediaResponse(BaseModel):
    message: str
    images: List[Dict[str, Any]]
    videos: List[Dict[str, Any]]
    signature_expiry: Optional[dt.datetime] = None

class GenerateSignedUrlRequest(BaseModel):
    url: str
    method: Optional[str] = 'GET'
    content_type: Optional[str] = None

class GenerateSignedUrlResponse(BaseModel):
    message: str
    url: str

class UpdateProjectRequest(BaseModel):
    project_id: str
    name: Optional[str]=None

class UpdateProjectResponse(BaseModel):
    message: str
    
class DeleteProjectRequest(BaseModel):
    project_id: str

class DeleteProjectResponse(BaseModel):
    message: str
    
class DeleteVideoRequest(BaseModel):
    project_id: str
    version_id: str

class DeleteVideoResponse(BaseModel):
    message: str

class DownloadVideoRequest(GenerateSignedUrlRequest):
    pass

class DownloadVideoResponse(GenerateSignedUrlResponse):
    pass

class RenderVideoRequest(BaseModel):
    token: str

class RenderVideoResponse(BaseModel):
    redirect_url: str


class ToggleFavouriteRequest(BaseModel):
    project_id: str
    version_id: str

class ToggleFavouriteResponse(BaseModel):
    message: str

class FetchUsedImagesRequest(BaseModel):
    project_id: str
    version_id: str
    
class FetchUsedImagesResponse(BaseModel):
    message: str
    used_images_url: List[Dict[str, Any]]

class UpdateViewRequest(BaseModel):
    project_id: str
    version_id: str

class UpdateViewResponse(BaseModel):
    message: str
    
class ExcludeMediaFilesRequest(BaseModel):
    project_id: str
    gs_urls: list[str]

class ExcludeMediaFilesResponse(BaseModel):
    message: str
    
class GetShareableLinkRequest(BaseModel):
    project_id: str
    version_id: str

class GetShareableLinkResponse(BaseModel):
    message: str
    link: str

class GetVideoDataRequest(BaseModel):
    token: str

class GetVideoDataResponse(BaseModel):
    message: str
    data: Dict[str, Any]

class PreselectImagesRequest(BaseModel):
    user_id: str
    project_id: str
    template: str

class PreselectImagesResponse(BaseModel):
    message: str
    images: List[Dict[str, Any]]
    
class FetchEDLSResponse(BaseModel):
    message: str
    edls: List[Dict[str, Any]]

class FetchVoicesResponse(BaseModel):
    message: str
    voices: List[Dict[str, Any]]

class FetchVideosResponse(BaseModel):
    message: str
    videos: List[Dict[str, Any]]

class FetchAllProjectsSlimResponse(BaseModel):
    message: str
    projects: List[Dict[str, Any]]
    
class FetchProjectResponse(BaseModel):
    message: str
    project: Dict[str, Any]

# NEW: Video upload and processing models
class UploadVideoRequest(BaseModel):
    project_id: str
    scene_detection_threshold: Optional[float] = 0.3
    max_scenes: Optional[int] = 20

class UploadVideoResponse(BaseModel):
    message: str
    video_id: str
    status: str  # "processing" | "completed" | "failed"
    estimated_processing_time: Optional[int] = None  # seconds

class VideoMetadata(BaseModel):
    duration: float
    fps: int
    resolution: List[int]  # [width, height]
    aspect_ratio: float
    orientation: str  # "landscape" | "portrait"
    has_audio: bool
    file_size_mb: float

class SceneClipTiming(BaseModel):
    start_time: float
    end_time: float
    duration: float

class SceneClipClassification(BaseModel):
    content_type: str  # "exterior", "interior", etc.
    quality_score: float
    visual_features: List[str]
    lighting_quality: str
    camera_movement: str
    composition_score: float
    motion_quality: float  # NEW for videos
    duration_fitness: float  # NEW for videos
    temporal_coherence: float  # NEW for videos

class SceneClipUsage(BaseModel):
    is_selected: bool = True
    is_excluded: bool = False
    selection_rank: Optional[int] = None
    last_used_in_template: Optional[str] = None

class SceneClip(BaseModel):
    scene_id: str
    parent_video_id: str
    gs_url: str
    signed_url: Optional[str] = None  # Lazy loaded
    thumbnail_url: Optional[str] = None  # Lazy loaded
    timing: SceneClipTiming
    classification: Optional[SceneClipClassification] = None  # Lazy loaded
    metadata: VideoMetadata
    usage: SceneClipUsage = SceneClipUsage()
    created_at: dt.datetime

class VideoProcessingStatus(BaseModel):
    video_id: str
    status: str  # "queued" | "processing" | "completed" | "failed"
    progress: int = 0
    processing_stages: Dict[str, Any] = {}
    scene_detection_results: Optional[Dict[str, Any]] = None  # Lazy loaded
    error_details: Optional[str] = None
    estimated_completion: Optional[dt.datetime] = None

class UploadedVideo(BaseModel):
    video_id: str
    filename: str
    gs_url: str
    metadata: VideoMetadata
    processing_status: str
    uploaded_at: dt.datetime
    scene_clips: Optional[List[SceneClip]] = None  # Lazy loaded

class ProjectVideosResponse(BaseModel):
    message: str
    videos: List[UploadedVideo]
    scene_clips: Optional[List[SceneClip]] = None  # Lazy loaded
    total_scene_clips: int = 0
    selected_scene_clips: int = 0

class VideoProcessingStatusResponse(BaseModel):
    message: str
    status: VideoProcessingStatus
