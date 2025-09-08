from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database.models.project import Project, ProjectVersion
from database.repository.base_repository import BaseRepository
from logger import logger


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project model"""
    
    def __init__(self, db_session: Session):
        super().__init__(Project, db_session)
    
    def get_by_user_id(self, user_id: str, limit: Optional[int] = None) -> List[Project]:
        """Get all projects for a specific user"""
        try:
            query = self.db_session.query(Project).filter(Project.user_id == user_id)
            if limit:
                query = query.limit(limit)
            projects = query.all()
            logger.debug(f"[PROJECT_REPOSITORY] Found {len(projects)} projects for user: {user_id}")
            return projects
        except SQLAlchemyError as e:
            logger.exception(f"[PROJECT_REPOSITORY] Failed to get projects for user {user_id}: {e}")
            return []
    
    def get_active_projects(self, user_id: str) -> List[Project]:
        """Get active projects for a user"""
        return self.get_by_filter(user_id=user_id, status='active')
    
    def archive_project(self, project_id: str) -> Optional[Project]:
        """Archive a project (set status to archived)"""
        return self.update(project_id, status='archived')


class ProjectVersionRepository(BaseRepository[ProjectVersion]):
    """Repository for ProjectVersion model"""
    
    def __init__(self, db_session: Session):
        super().__init__(ProjectVersion, db_session)
    
    def get_by_project_id(self, project_id: str) -> List[ProjectVersion]:
        """Get all versions for a specific project"""
        return self.get_by_filter(project_id=project_id)
    
    def get_current_version(self, project_id: str) -> Optional[ProjectVersion]:
        """Get the current version of a project"""
        try:
            version = self.db_session.query(ProjectVersion).filter(
                ProjectVersion.project_id == project_id,
                ProjectVersion.is_current == True
            ).first()
            logger.debug(f"[PROJECT_VERSION_REPOSITORY] Current version for project {project_id}: {version.id if version else 'None'}")
            return version
        except SQLAlchemyError as e:
            logger.exception(f"[PROJECT_VERSION_REPOSITORY] Failed to get current version for project {project_id}: {e}")
            return None
    
    def set_current_version(self, project_id: str, version_id: str) -> bool:
        """Set a version as the current version for a project"""
        try:
            # First, unset all current versions for this project
            self.db_session.query(ProjectVersion).filter(
                ProjectVersion.project_id == project_id
            ).update({'is_current': False})
            
            # Then set the specified version as current
            version = self.get_by_id(version_id)
            if version and version.project_id == project_id:
                version.is_current = True
                self.db_session.commit()
                logger.info(f"[PROJECT_VERSION_REPOSITORY] Set version {version_id} as current for project {project_id}")
                return True
            return False
        except SQLAlchemyError as e:
            logger.exception(f"[PROJECT_VERSION_REPOSITORY] Failed to set current version {version_id} for project {project_id}: {e}")
            self.db_session.rollback()
            return False
