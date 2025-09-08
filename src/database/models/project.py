from sqlalchemy import Column, String, Text, JSON, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from database.models.base import Base


class Project(Base):
    """Project model - corresponds to Firestore projects collection"""
    __tablename__ = "projects"
    
    # Project identification
    user_id = Column(String, nullable=False, index=True)  # Reference to user (managed by another service)
    name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    
    # Project configuration
    status = Column(String, default="active", nullable=False)  # active, archived, deleted
    settings = Column(JSON, default=dict)  # Project-specific settings
    
    # Template and style information
    template_id = Column(String, nullable=True)
    style_preferences = Column(JSON, default=dict)
    
    # Relationships
    versions = relationship("ProjectVersion", back_populates="project", cascade="all, delete-orphan")
    properties = relationship("Property", back_populates="project", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="project", cascade="all, delete-orphan")


class ProjectVersion(Base):
    """Project version model - corresponds to Firestore versions subcollection"""
    __tablename__ = "project_versions"
    
    # Version identification
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    name = Column(String, nullable=True)
    
    # Version status and metadata
    status = Column(String, default="draft", nullable=False)  # draft, processing, completed, failed
    is_current = Column(Boolean, default=False, nullable=False)
    
    # Version configuration
    configuration = Column(JSON, default=dict)
    processing_log = Column(JSON, default=list)  # Array of processing steps/logs
    
    # Output information
    output_urls = Column(JSON, default=dict)  # Generated video URLs, thumbnails, etc.
    
    # Relationships
    project = relationship("Project", back_populates="versions")
    movies = relationship("Movie", back_populates="project_version", cascade="all, delete-orphan")
    videos = relationship("Video", back_populates="project_version", cascade="all, delete-orphan")
