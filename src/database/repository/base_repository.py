from typing import Generic, TypeVar, Type, Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from database.models.base import Base
from logger import logger

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository class with common CRUD operations"""
    
    def __init__(self, model: Type[ModelType], db_session: Session):
        self.model = model
        self.db_session = db_session
    
    def create(self, **kwargs) -> Optional[ModelType]:
        """Create a new record"""
        try:
            obj = self.model(**kwargs)
            self.db_session.add(obj)
            self.db_session.commit()
            self.db_session.refresh(obj)
            logger.info(f"[{self.__class__.__name__}] Created {self.model.__name__} with id: {obj.id}")
            return obj
        except SQLAlchemyError as e:
            logger.exception(f"[{self.__class__.__name__}] Failed to create {self.model.__name__}: {e}")
            self.db_session.rollback()
            return None
    
    def get_by_id(self, id: str) -> Optional[ModelType]:
        """Get record by ID"""
        try:
            obj = self.db_session.query(self.model).filter(self.model.id == id).first()
            if obj:
                logger.debug(f"[{self.__class__.__name__}] Found {self.model.__name__} with id: {id}")
            else:
                logger.warning(f"[{self.__class__.__name__}] {self.model.__name__} not found with id: {id}")
            return obj
        except SQLAlchemyError as e:
            logger.exception(f"[{self.__class__.__name__}] Failed to get {self.model.__name__} by id {id}: {e}")
            return None
    
    def get_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[ModelType]:
        """Get all records with optional pagination"""
        try:
            query = self.db_session.query(self.model)
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            results = query.all()
            logger.debug(f"[{self.__class__.__name__}] Found {len(results)} {self.model.__name__} records")
            return results
        except SQLAlchemyError as e:
            logger.exception(f"[{self.__class__.__name__}] Failed to get all {self.model.__name__}: {e}")
            return []
    
    def get_by_filter(self, **filters) -> List[ModelType]:
        """Get records by filter criteria"""
        try:
            query = self.db_session.query(self.model)
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)
            results = query.all()
            logger.debug(f"[{self.__class__.__name__}] Found {len(results)} {self.model.__name__} records with filters: {filters}")
            return results
        except SQLAlchemyError as e:
            logger.exception(f"[{self.__class__.__name__}] Failed to get {self.model.__name__} by filter {filters}: {e}")
            return []
    
    def update(self, id: str, **kwargs) -> Optional[ModelType]:
        """Update record by ID"""
        try:
            obj = self.get_by_id(id)
            if not obj:
                return None
            
            for key, value in kwargs.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)
            
            self.db_session.commit()
            self.db_session.refresh(obj)
            logger.info(f"[{self.__class__.__name__}] Updated {self.model.__name__} with id: {id}")
            return obj
        except SQLAlchemyError as e:
            logger.exception(f"[{self.__class__.__name__}] Failed to update {self.model.__name__} with id {id}: {e}")
            self.db_session.rollback()
            return None
    
    def delete(self, id: str) -> bool:
        """Delete record by ID"""
        try:
            obj = self.get_by_id(id)
            if not obj:
                return False
            
            self.db_session.delete(obj)
            self.db_session.commit()
            logger.info(f"[{self.__class__.__name__}] Deleted {self.model.__name__} with id: {id}")
            return True
        except SQLAlchemyError as e:
            logger.exception(f"[{self.__class__.__name__}] Failed to delete {self.model.__name__} with id {id}: {e}")
            self.db_session.rollback()
            return False
    
    def count(self, **filters) -> int:
        """Count records with optional filters"""
        try:
            query = self.db_session.query(self.model)
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)
            count = query.count()
            logger.debug(f"[{self.__class__.__name__}] Count of {self.model.__name__} with filters {filters}: {count}")
            return count
        except SQLAlchemyError as e:
            logger.exception(f"[{self.__class__.__name__}] Failed to count {self.model.__name__} with filters {filters}: {e}")
            return 0
    
    def exists(self, id: str) -> bool:
        """Check if record exists by ID"""
        try:
            exists = self.db_session.query(self.model.id).filter(self.model.id == id).first() is not None
            logger.debug(f"[{self.__class__.__name__}] {self.model.__name__} exists with id {id}: {exists}")
            return exists
        except SQLAlchemyError as e:
            logger.exception(f"[{self.__class__.__name__}] Failed to check existence of {self.model.__name__} with id {id}: {e}")
            return False
