from sqlalchemy import Column, String, Text, JSON, DateTime, ForeignKey, Float, Integer, Boolean
from sqlalchemy.orm import relationship
from database.models.base import Base


class Movie(Base):
    """Movie model - corresponds to Firestore movies collection"""
    __tablename__ = "movies"
    
    # Movie identification and relationships
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    project_version_id = Column(String, ForeignKey("project_versions.id"), nullable=True, index=True)
    user_id = Column(String, nullable=False, index=True)  # Reference to user
    
    # Movie metadata
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    
    # Movie specifications
    duration = Column(Float, nullable=True)  # Duration in seconds
    resolution_width = Column(Integer, nullable=True)
    resolution_height = Column(Integer, nullable=True)
    frame_rate = Column(Float, default=30.0, nullable=False)
    orientation = Column(String, nullable=True)  # landscape, portrait, square
    
    # Movie status and processing
    status = Column(String, default="pending", nullable=False)  # pending, processing, completed, failed
    processing_progress = Column(Integer, default=0, nullable=False)  # 0-100
    
    # Template and style information
    template_id = Column(String, nullable=True)
    template_data = Column(JSON, default=dict)  # Template configuration used
    edl_data = Column(JSON, default=dict)  # Edit Decision List data
    
    # Audio and voiceover
    has_voiceover = Column(Boolean, default=False, nullable=False)
    voiceover_config = Column(JSON, default=dict)  # Voiceover settings and metadata
    background_music = Column(JSON, default=dict)  # Background music configuration
    audio_levels = Column(JSON, default=dict)  # Audio level settings
    
    # Visual elements
    captions_config = Column(JSON, default=dict)  # Caption settings
    effects_config = Column(JSON, default=dict)  # Visual effects configuration
    watermark_config = Column(JSON, default=dict)  # Watermark settings
    
    # File locations and URLs
    output_url = Column(Text, nullable=True)  # Final movie URL
    preview_url = Column(Text, nullable=True)  # Preview/thumbnail URL
    source_files = Column(JSON, default=list)  # Array of source file URLs
    
    # Processing metadata
    processing_log = Column(JSON, default=list)  # Array of processing steps
    error_log = Column(JSON, default=list)  # Array of errors encountered
    
    # Timing information
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    render_time = Column(Float, nullable=True)  # Render time in seconds
    
    # Quality and optimization
    quality_settings = Column(JSON, default=dict)  # Quality and compression settings
    file_size = Column(Integer, nullable=True)  # File size in bytes
    
    # Relationships
    session = relationship("Session", back_populates="movies")
    project_version = relationship("ProjectVersion", back_populates="movies")
