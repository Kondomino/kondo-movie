from sqlalchemy import Column, String, Text, JSON, Boolean, DateTime, ForeignKey, Float, Integer
from sqlalchemy.orm import relationship
from database.models.base import Base


class Property(Base):
    """Property model - corresponds to Firestore properties collection"""
    __tablename__ = "properties"
    
    # Property identification
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    
    # Address and location information
    address = Column(Text, nullable=False)
    formatted_address = Column(Text, nullable=True)
    place_id = Column(String, nullable=True)  # Google Places ID
    
    # Geographic coordinates
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Address components (from Google Places API)
    address_components = Column(JSON, default=dict)
    
    # Property details
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    property_type = Column(String, nullable=True)  # house, apartment, condo, etc.
    
    # Property features and specifications
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Float, nullable=True)
    square_feet = Column(Integer, nullable=True)
    lot_size = Column(Float, nullable=True)
    year_built = Column(Integer, nullable=True)
    
    # Pricing information
    price = Column(Float, nullable=True)
    price_currency = Column(String, default="USD", nullable=False)
    price_type = Column(String, nullable=True)  # sale, rent, estimate
    
    # Property status and metadata
    status = Column(String, default="active", nullable=False)  # active, sold, off_market, deleted
    listing_agent = Column(String, nullable=True)
    listing_agency = Column(String, nullable=True)
    mls_number = Column(String, nullable=True)
    
    # Scraping and extraction metadata
    source_url = Column(Text, nullable=True)
    tenant_id = Column(String, nullable=True)  # Which scraper/tenant extracted this
    extraction_time = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, nullable=True)
    
    # Media and assets
    images = Column(JSON, default=list)  # Array of image URLs/paths
    videos = Column(JSON, default=list)  # Array of video URLs/paths
    virtual_tours = Column(JSON, default=list)  # Virtual tour URLs
    
    # Classification and AI analysis
    classification_data = Column(JSON, default=dict)  # AI classification results
    image_analysis = Column(JSON, default=dict)  # Image analysis results
    
    # Additional property features and amenities
    features = Column(JSON, default=list)  # Array of property features
    amenities = Column(JSON, default=list)  # Array of amenities
    
    # Relationships
    project = relationship("Project", back_populates="properties")
