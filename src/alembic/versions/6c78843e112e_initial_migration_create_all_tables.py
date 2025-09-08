"""Initial migration: Create all tables

Revision ID: 6c78843e112e
Revises: 
Create Date: 2025-09-05 09:26:56.494308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c78843e112e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create projects table
    op.create_table('projects',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('metadata', sa.JSON(), default={}),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, default='active'),
        sa.Column('settings', sa.JSON(), default={}),
        sa.Column('template_id', sa.String(), nullable=True),
        sa.Column('style_preferences', sa.JSON(), default={})
    )
    op.create_index('ix_projects_user_id', 'projects', ['user_id'])
    
    # Create project_versions table
    op.create_table('project_versions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('metadata', sa.JSON(), default={}),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, default='draft'),
        sa.Column('is_current', sa.Boolean(), nullable=False, default=False),
        sa.Column('configuration', sa.JSON(), default={}),
        sa.Column('processing_log', sa.JSON(), default=[]),
        sa.Column('output_urls', sa.JSON(), default={})
    )
    op.create_index('ix_project_versions_project_id', 'project_versions', ['project_id'])
    
    # Create properties table
    op.create_table('properties',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('metadata', sa.JSON(), default={}),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('formatted_address', sa.Text(), nullable=True),
        sa.Column('place_id', sa.String(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('address_components', sa.JSON(), default={}),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('property_type', sa.String(), nullable=True),
        sa.Column('bedrooms', sa.Integer(), nullable=True),
        sa.Column('bathrooms', sa.Float(), nullable=True),
        sa.Column('square_feet', sa.Integer(), nullable=True),
        sa.Column('lot_size', sa.Float(), nullable=True),
        sa.Column('year_built', sa.Integer(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('price_currency', sa.String(), nullable=False, default='USD'),
        sa.Column('price_type', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, default='active'),
        sa.Column('listing_agent', sa.String(), nullable=True),
        sa.Column('listing_agency', sa.String(), nullable=True),
        sa.Column('mls_number', sa.String(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('extraction_time', sa.DateTime(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('images', sa.JSON(), default=[]),
        sa.Column('videos', sa.JSON(), default=[]),
        sa.Column('virtual_tours', sa.JSON(), default=[]),
        sa.Column('classification_data', sa.JSON(), default={}),
        sa.Column('image_analysis', sa.JSON(), default={}),
        sa.Column('features', sa.JSON(), default=[]),
        sa.Column('amenities', sa.JSON(), default=[])
    )
    op.create_index('ix_properties_project_id', 'properties', ['project_id'])
    
    # Create sessions table
    op.create_table('sessions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('metadata', sa.JSON(), default={}),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('session_type', sa.String(), nullable=False, default='movie_generation'),
        sa.Column('status', sa.String(), nullable=False, default='active'),
        sa.Column('progress_percentage', sa.Integer(), nullable=False, default=0),
        sa.Column('configuration', sa.JSON(), default={}),
        sa.Column('input_parameters', sa.JSON(), default={}),
        sa.Column('processing_log', sa.JSON(), default=[]),
        sa.Column('error_log', sa.JSON(), default=[]),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('estimated_completion', sa.DateTime(), nullable=True),
        sa.Column('output_data', sa.JSON(), default={}),
        sa.Column('generated_assets', sa.JSON(), default=[])
    )
    op.create_index('ix_sessions_project_id', 'sessions', ['project_id'])
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])
    
    # Create movies table
    op.create_table('movies',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('metadata', sa.JSON(), default={}),
        sa.Column('session_id', sa.String(), sa.ForeignKey('sessions.id'), nullable=False),
        sa.Column('project_version_id', sa.String(), sa.ForeignKey('project_versions.id'), nullable=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('resolution_width', sa.Integer(), nullable=True),
        sa.Column('resolution_height', sa.Integer(), nullable=True),
        sa.Column('frame_rate', sa.Float(), nullable=False, default=30.0),
        sa.Column('orientation', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, default='pending'),
        sa.Column('processing_progress', sa.Integer(), nullable=False, default=0),
        sa.Column('template_id', sa.String(), nullable=True),
        sa.Column('template_data', sa.JSON(), default={}),
        sa.Column('edl_data', sa.JSON(), default={}),
        sa.Column('has_voiceover', sa.Boolean(), nullable=False, default=False),
        sa.Column('voiceover_config', sa.JSON(), default={}),
        sa.Column('background_music', sa.JSON(), default={}),
        sa.Column('audio_levels', sa.JSON(), default={}),
        sa.Column('captions_config', sa.JSON(), default={}),
        sa.Column('effects_config', sa.JSON(), default={}),
        sa.Column('watermark_config', sa.JSON(), default={}),
        sa.Column('output_url', sa.Text(), nullable=True),
        sa.Column('preview_url', sa.Text(), nullable=True),
        sa.Column('source_files', sa.JSON(), default=[]),
        sa.Column('processing_log', sa.JSON(), default=[]),
        sa.Column('error_log', sa.JSON(), default=[]),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('render_time', sa.Float(), nullable=True),
        sa.Column('quality_settings', sa.JSON(), default={}),
        sa.Column('file_size', sa.Integer(), nullable=True)
    )
    op.create_index('ix_movies_session_id', 'movies', ['session_id'])
    op.create_index('ix_movies_project_version_id', 'movies', ['project_version_id'])
    op.create_index('ix_movies_user_id', 'movies', ['user_id'])
    
    # Create videos table
    op.create_table('videos',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('metadata', sa.JSON(), default={}),
        sa.Column('session_id', sa.String(), sa.ForeignKey('sessions.id'), nullable=True),
        sa.Column('project_version_id', sa.String(), sa.ForeignKey('project_versions.id'), nullable=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('original_filename', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('frame_rate', sa.Float(), nullable=True),
        sa.Column('bitrate', sa.Integer(), nullable=True),
        sa.Column('codec', sa.String(), nullable=True),
        sa.Column('format', sa.String(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_url', sa.Text(), nullable=False),
        sa.Column('thumbnail_url', sa.Text(), nullable=True),
        sa.Column('video_type', sa.String(), nullable=False, default='uploaded'),
        sa.Column('source_video_id', sa.String(), nullable=True),
        sa.Column('scene_number', sa.Integer(), nullable=True),
        sa.Column('scene_start_time', sa.Float(), nullable=True),
        sa.Column('scene_end_time', sa.Float(), nullable=True),
        sa.Column('scene_confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, default='uploaded'),
        sa.Column('processing_progress', sa.Integer(), nullable=False, default=0),
        sa.Column('is_classified', sa.Boolean(), nullable=False, default=False),
        sa.Column('classification_data', sa.JSON(), default={}),
        sa.Column('keyframes', sa.JSON(), default=[]),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('technical_metadata', sa.JSON(), default={}),
        sa.Column('processing_config', sa.JSON(), default={}),
        sa.Column('scene_detection_config', sa.JSON(), default={}),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('processing_errors', sa.JSON(), default=[])
    )
    op.create_index('ix_videos_session_id', 'videos', ['session_id'])
    op.create_index('ix_videos_project_version_id', 'videos', ['project_version_id'])
    op.create_index('ix_videos_user_id', 'videos', ['user_id'])
    op.create_index('ix_videos_project_id', 'videos', ['project_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables in reverse order (due to foreign key constraints)
    op.drop_table('videos')
    op.drop_table('movies')
    op.drop_table('sessions')
    op.drop_table('properties')
    op.drop_table('project_versions')
    op.drop_table('projects')
