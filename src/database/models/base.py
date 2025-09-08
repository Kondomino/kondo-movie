from datetime import datetime
from typing import Any, Dict
from sqlalchemy import Column, String, DateTime, JSON, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.declarative import declared_attr


class BaseModel:
    """Base model with common fields and methods"""
    
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()
    
    # Common fields that match Firestore document structure
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Metadata field to store additional Firestore-like data
    metadata = Column(JSON, default=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary (similar to Firestore document)"""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result
    
    def update_from_dict(self, data: Dict[str, Any]):
        """Update model from dictionary"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(id='{self.id}')>"


# Create the base class for all models
Base = declarative_base(cls=BaseModel)
