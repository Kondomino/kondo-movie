#!/usr/bin/env python3
"""
Production Database Configuration Tests

Tests that validate production database configuration parsing
and connection string generation without making actual connections.
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

@contextmanager
def mock_environment(env_vars: dict):
    """Context manager to temporarily set environment variables"""
    original_values = {}
    
    # Store original values
    for key in env_vars:
        original_values[key] = os.environ.get(key)
    
    # Set new values
    for key, value in env_vars.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = str(value)
    
    try:
        yield
    finally:
        # Restore original values
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value

def test_production_environment_detection():
    """Test that production environment is detected correctly"""
    with mock_environment({'ENVIRONMENT': 'prod'}):
        from database.database_manager import DatabaseManager
        
        # Create a fresh instance to test environment detection
        manager = DatabaseManager.__new__(DatabaseManager)
        manager.setup()
        
        assert manager.environment == 'prod'
        assert manager.provider == 'PostgreSQL'

def test_render_database_url_from_individual_vars():
    """Test database URL construction from individual RENDER_* variables"""
    render_vars = {
        'ENVIRONMENT': 'prod',
        'RENDER_HOSTNAME': 'test-host.render.com',
        'RENDER_DB_PORT': '5432',
        'RENDER_USR': 'testuser',
        'RENDER_PWD': 'testpass',
        'RENDER_DB': 'testdb'
    }
    
    with mock_environment(render_vars):
        from database.database_manager import DatabaseManager
        
        # Mock SQLAlchemy to prevent actual connection
        with patch('database.database_manager.create_engine') as mock_engine:
            mock_engine.return_value = MagicMock()
            
            manager = DatabaseManager.__new__(DatabaseManager)
            manager.setup()
            
            # Test that the correct database URL was constructed
            expected_url = "postgresql://testuser:testpass@test-host.render.com:5432/testdb?sslmode=require"
            
            # The database URL should be passed to create_engine
            mock_engine.assert_called_once()
            actual_url = mock_engine.call_args[0][0]
            assert actual_url == expected_url

def test_render_database_url_from_complete_url():
    """Test database URL usage when RENDER_INTERNAL_URL is provided"""
    render_vars = {
        'ENVIRONMENT': 'prod',
        'RENDER_INTERNAL_URL': 'postgresql://user:pass@host.render.com:5432/dbname'
    }
    
    with mock_environment(render_vars):
        from database.database_manager import DatabaseManager
        
        with patch('database.database_manager.create_engine') as mock_engine:
            mock_engine.return_value = MagicMock()
            
            manager = DatabaseManager.__new__(DatabaseManager)
            manager.setup()
            
            # Should use the complete URL directly
            mock_engine.assert_called_once()
            actual_url = mock_engine.call_args[0][0]
            assert actual_url == 'postgresql://user:pass@host.render.com:5432/dbname'

def test_ssl_requirements_in_production():
    """Test that SSL is required in production environment"""
    render_vars = {
        'ENVIRONMENT': 'prod',
        'RENDER_HOSTNAME': 'test-host.render.com',
        'RENDER_DB_PORT': '5432',
        'RENDER_USR': 'testuser',
        'RENDER_PWD': 'testpass',
        'RENDER_DB': 'testdb'
    }
    
    with mock_environment(render_vars):
        from database.database_manager import DatabaseManager
        
        with patch('database.database_manager.create_engine') as mock_engine:
            mock_engine.return_value = MagicMock()
            
            manager = DatabaseManager.__new__(DatabaseManager)
            manager.setup()
            
            # Check that SSL is required in the connection string
            actual_url = mock_engine.call_args[0][0]
            assert 'sslmode=require' in actual_url

def test_missing_render_credentials_handling():
    """Test error handling when required RENDER_* variables are missing"""
    incomplete_vars = {
        'ENVIRONMENT': 'prod',
        'RENDER_HOSTNAME': 'test-host.render.com',
        # Missing RENDER_USR, RENDER_PWD, RENDER_DB
    }
    
    with mock_environment(incomplete_vars):
        from database.database_manager import DatabaseManager
        
        with pytest.raises(ValueError, match="Missing required production database configuration"):
            manager = DatabaseManager.__new__(DatabaseManager)
            manager.setup()

def test_database_url_priority_order():
    """Test that DATABASE_URL takes priority over RENDER_* variables"""
    all_vars = {
        'ENVIRONMENT': 'prod',
        'DATABASE_URL': 'postgresql://priority:user@priority.host:5432/priority_db',
        'RENDER_INTERNAL_URL': 'postgresql://internal:user@internal.host:5432/internal_db',
        'RENDER_HOSTNAME': 'fallback-host.render.com',
        'RENDER_USR': 'fallback_user',
        'RENDER_PWD': 'fallback_pass',
        'RENDER_DB': 'fallback_db'
    }
    
    with mock_environment(all_vars):
        from database.database_manager import DatabaseManager
        
        with patch('database.database_manager.create_engine') as mock_engine:
            mock_engine.return_value = MagicMock()
            
            manager = DatabaseManager.__new__(DatabaseManager)
            manager.setup()
            
            # Should use DATABASE_URL (highest priority)
            actual_url = mock_engine.call_args[0][0]
            assert actual_url == 'postgresql://priority:user@priority.host:5432/priority_db'

def test_render_internal_url_priority():
    """Test that RENDER_INTERNAL_URL takes priority over individual RENDER_* vars"""
    vars_with_internal_url = {
        'ENVIRONMENT': 'prod',
        'RENDER_INTERNAL_URL': 'postgresql://internal:user@internal.host:5432/internal_db',
        'RENDER_HOSTNAME': 'fallback-host.render.com',
        'RENDER_USR': 'fallback_user',
        'RENDER_PWD': 'fallback_pass',
        'RENDER_DB': 'fallback_db'
    }
    
    with mock_environment(vars_with_internal_url):
        from database.database_manager import DatabaseManager
        
        with patch('database.database_manager.create_engine') as mock_engine:
            mock_engine.return_value = MagicMock()
            
            manager = DatabaseManager.__new__(DatabaseManager)
            manager.setup()
            
            # Should use RENDER_INTERNAL_URL
            actual_url = mock_engine.call_args[0][0]
            assert actual_url == 'postgresql://internal:user@internal.host:5432/internal_db'

def validate_database_url(url: str, expected_components: dict):
    """Helper function to validate database URL components"""
    import re
    
    # Parse PostgreSQL URL: postgresql://user:pass@host:port/database?params
    pattern = r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/([^?]+)(?:\?(.+))?'
    match = re.match(pattern, url)
    
    if not match:
        raise ValueError(f"Invalid PostgreSQL URL format: {url}")
    
    user, password, host, port, database, params = match.groups()
    
    actual_components = {
        'user': user,
        'password': password, 
        'host': host,
        'port': int(port),
        'database': database,
        'params': params or ''
    }
    
    for key, expected_value in expected_components.items():
        actual_value = actual_components.get(key)
        assert actual_value == expected_value, f"Expected {key}={expected_value}, got {actual_value}"

def test_database_url_component_validation():
    """Test that database URL components are correctly parsed"""
    render_vars = {
        'ENVIRONMENT': 'prod',
        'RENDER_HOSTNAME': 'my-db.render.com',
        'RENDER_DB_PORT': '5432',
        'RENDER_USR': 'myuser',
        'RENDER_PWD': 'mypassword',
        'RENDER_DB': 'mydatabase'
    }
    
    with mock_environment(render_vars):
        from database.database_manager import DatabaseManager
        
        with patch('database.database_manager.create_engine') as mock_engine:
            mock_engine.return_value = MagicMock()
            
            manager = DatabaseManager.__new__(DatabaseManager)
            manager.setup()
            
            actual_url = mock_engine.call_args[0][0]
            
            validate_database_url(actual_url, {
                'user': 'myuser',
                'password': 'mypassword',
                'host': 'my-db.render.com',
                'port': 5432,
                'database': 'mydatabase',
                'params': 'sslmode=require'
            })

if __name__ == '__main__':
    # Run the tests
    pytest.main([__file__, '-v'])
