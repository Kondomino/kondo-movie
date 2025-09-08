import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, create_engine
from sqlalchemy import pool

from alembic import context

# Add the src directory to the Python path so we can import our models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our models for autogenerate support
from database.models.base import Base
from database.models.project import Project, ProjectVersion
from database.models.property import Property
from database.models.session import Session
from database.models.movie import Movie
from database.models.video import Video

# Import configuration
from config.config import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target_metadata for autogenerate support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get database URL based on environment"""
    environment = os.getenv('ENVIRONMENT', 'dev')
    
    print(f"[ALEMBIC] Environment: {environment}")
    print(f"[ALEMBIC] All environment variables starting with DB_:")
    for key, value in os.environ.items():
        if key.startswith('DB_'):
            if 'PASSWORD' in key:
                print(f"[ALEMBIC]   {key}: ***")
            else:
                print(f"[ALEMBIC]   {key}: {value}")
    
    if environment == 'prod':
        # Production: Try DATABASE_URL first, then RENDER_* vars
        database_url = (
            os.getenv('DATABASE_URL') or 
            os.getenv('RENDER_INTERNAL_URL') or 
            os.getenv('RENDER_EXTERNAL_URL')
        )
        
        if database_url:
            return database_url
        
        # Fallback to individual RENDER_* environment variables
        host = os.getenv('RENDER_HOSTNAME')
        port = os.getenv('RENDER_DB_PORT', '5432')
        username = os.getenv('RENDER_USR')
        password = os.getenv('RENDER_PWD')
        database = os.getenv('RENDER_DB')
        
        if all([host, username, password, database]):
            return f"postgresql://{username}:{password}@{host}:{port}/{database}?sslmode=require"
        else:
            raise ValueError("Missing required RENDER_* environment variables for production database")
    
    else:
        # Development: Local container
        host = os.getenv('DB_HOST', settings.PostgreSQL.DEV.HOST)
        port = os.getenv('DB_PORT', str(settings.PostgreSQL.DEV.PORT))
        username = os.getenv('DB_USER', 'postgres')
        password = os.getenv('DB_PASSWORD', 'postgres')
        database = os.getenv('DB_NAME', settings.PostgreSQL.DEV.DATABASE)
        
        ssl_mode = "disable" if not settings.PostgreSQL.DEV.SSL_REQUIRED else "require"
        
        print(f"[ALEMBIC] Development database configuration:")
        print(f"[ALEMBIC]   Host: {host} (from env: {os.getenv('DB_HOST', 'NOT SET')}, config: {settings.PostgreSQL.DEV.HOST})")
        print(f"[ALEMBIC]   Port: {port} (from env: {os.getenv('DB_PORT', 'NOT SET')}, config: {settings.PostgreSQL.DEV.PORT})")
        print(f"[ALEMBIC]   Username: {username} (from env: {os.getenv('DB_USER', 'NOT SET')})")
        print(f"[ALEMBIC]   Password: {'***' if password else 'NOT SET'} (from env: {'***' if os.getenv('DB_PASSWORD') else 'NOT SET'})")
        print(f"[ALEMBIC]   Database: {database} (from env: {os.getenv('DB_NAME', 'NOT SET')}, config: {settings.PostgreSQL.DEV.DATABASE})")
        print(f"[ALEMBIC]   SSL Mode: {ssl_mode}")
        
        database_url = f"postgresql://{username}:{password}@{host}:{port}/{database}?sslmode={ssl_mode}"
        print(f"[ALEMBIC] Final database URL: postgresql://{username}:***@{host}:{port}/{database}?sslmode={ssl_mode}")
        
        return database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get database URL based on environment
    database_url = get_database_url()
    
    # Create engine with the environment-specific URL
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()