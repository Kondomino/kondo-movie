from sqlalchemy import Column, String, Text, JSON, DateTime, ForeignKey, Float, Integer, Boolean
from sqlalchemy.orm import relationship
from database.models.base import Base


class Video(Base):
    """Video model - corresponds to video assets and processing"""
    __tablename__ = "videos"
    
    # Video identification and relationships
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True, index=True)
    project_version_id = Column(String, ForeignKey("project_versions.id"), nullable=True, index=True)
    user_id = Column(String, nullable=False, index=True)  # Reference to user
    project_id = Column(String, nullable=False, index=True)  # Reference to project
    
    # Video metadata
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    
    # Video specifications
    duration = Column(Float, nullable=True)  # Duration in seconds
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    frame_rate = Column(Float, nullable=True)
    bitrate = Column(Integer, nullable=True)
    codec = Column(String, nullable=True)
    format = Column(String, nullable=True)  # mp4, mov, webm, etc.
    
    # File information
    file_size = Column(Integer, nullable=True)  # File size in bytes
    file_url = Column(Text, nullable=False)  # Storage URL
    thumbnail_url = Column(Text, nullable=True)  # Thumbnail URL
    
    # Video type and classification
    video_type = Column(String, default="uploaded", nullable=False)  # uploaded, scene_clip, processed
    source_video_id = Column(String, nullable=True)  # Reference to parent video if this is a clip
    
    # Scene and clip information (for scene clips)
    scene_number = Column(Integer, nullable=True)
    scene_start_time = Column(Float, nullable=True)  # Start time in source video
    scene_end_time = Column(Float, nullable=True)    # End time in source video
    scene_confidence = Column(Float, nullable=True)  # Scene detection confidence
    
    # Processing status
    status = Column(String, default="uploaded", nullable=False)  # uploaded, processing, processed, failed
    processing_progress = Column(Integer, default=0, nullable=False)  # 0-100
    
    # Classification and analysis
    is_classified = Column(Boolean, default=False, nullable=False)
    classification_data = Column(JSON, default=dict)  # AI classification results
    keyframes = Column(JSON, default=list)  # Array of keyframe URLs/timestamps
    
    # Quality and technical metadata
    quality_score = Column(Float, nullable=True)  # Quality assessment score
    technical_metadata = Column(JSON, default=dict)  # Technical video metadata
    
    # Processing configuration
    processing_config = Column(JSON, default=dict)  # Processing parameters used
    scene_detection_config = Column(JSON, default=dict)  # Scene detection settings
    
    # Upload and processing timing
    uploaded_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    
    # Error handling
    processing_errors = Column(JSON, default=list)  # Array of processing errors
    
    # Relationships
    session = relationship("Session", back_populates="videos")
    project_version = relationship("ProjectVersion", back_populates="videos")
