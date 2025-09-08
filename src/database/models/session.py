from sqlalchemy import Column, String, Text, JSON, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from database.models.base import Base


class Session(Base):
    """Session model - corresponds to Firestore sessions collection"""
    __tablename__ = "sessions"
    
    # Session identification and relationships
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)  # Reference to user
    
    # Session metadata
    name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    session_type = Column(String, default="movie_generation", nullable=False)  # movie_generation, video_processing, etc.
    
    # Session status and progress
    status = Column(String, default="active", nullable=False)  # active, processing, completed, failed, cancelled
    progress_percentage = Column(Integer, default=0, nullable=False)
    
    # Session configuration and parameters
    configuration = Column(JSON, default=dict)  # Session-specific settings
    input_parameters = Column(JSON, default=dict)  # Input parameters for processing
    
    # Processing information
    processing_log = Column(JSON, default=list)  # Array of processing steps and logs
    error_log = Column(JSON, default=list)  # Array of errors encountered
    
    # Timing information
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_completion = Column(DateTime, nullable=True)
    
    # Output and results
    output_data = Column(JSON, default=dict)  # Session output data
    generated_assets = Column(JSON, default=list)  # Array of generated asset URLs/paths
    
    # Relationships
    project = relationship("Project", back_populates="sessions")
    movies = relationship("Movie", back_populates="session", cascade="all, delete-orphan")
    videos = relationship("Video", back_populates="session", cascade="all, delete-orphan")
