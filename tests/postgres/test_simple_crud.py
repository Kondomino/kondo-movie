#!/usr/bin/env python3
"""
Simple test script to verify PostgreSQL CRUD operations using our new service layer.
This test demonstrates basic insertion and deletion operations.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

def test_simple_crud():
    """Test basic CRUD operations with PostgreSQL"""
    print("🧪 Testing Simple CRUD Operations...")
    
    try:
        # Import our service layer
        from services.project_service import project_service
        from database.db_manager import unified_db_manager
        
        print("✅ Successfully imported service layer")
        
        # Check if PostgreSQL is active
        if not unified_db_manager.is_postgresql_active():
            print("❌ PostgreSQL is not active - check your configuration")
            return False
        
        print("✅ PostgreSQL is active")
        
        # Test data
        user_id = "test_user_123"
        project_id = "test_project_456"
        project_data = {
            "name": "Test Project",
            "description": "A simple test project for CRUD operations",
            "status": "active",
            "template_id": "template_001",
            "settings": {
                "quality": "high",
                "format": "mp4"
            },
            "style_preferences": {
                "theme": "modern",
                "color_scheme": "blue"
            }
        }
        
        print(f"📝 Test data prepared:")
        print(f"   User ID: {user_id}")
        print(f"   Project ID: {project_id}")
        print(f"   Project Name: {project_data['name']}")
        
        # 1. CREATE - Insert a new project
        print("\n1️⃣ CREATE: Inserting new project...")
        created_project = project_service.create_project(user_id, project_id, project_data)
        
        if created_project:
            print("✅ Project created successfully!")
            print(f"   Created project ID: {created_project.get('id')}")
            print(f"   Created project name: {created_project.get('name')}")
        else:
            print("❌ Failed to create project")
            return False
        
        # 2. READ - Fetch the project
        print("\n2️⃣ READ: Fetching the project...")
        fetched_project = project_service.get_project(user_id, project_id)
        
        if fetched_project:
            print("✅ Project fetched successfully!")
            print(f"   Fetched project ID: {fetched_project.get('id')}")
            print(f"   Fetched project name: {fetched_project.get('name')}")
            print(f"   Fetched project status: {fetched_project.get('status')}")
        else:
            print("❌ Failed to fetch project")
            return False
        
        # 3. VERIFY - Check project exists
        print("\n3️⃣ VERIFY: Checking project existence...")
        exists = project_service.project_exists(user_id, project_id)
        
        if exists:
            print("✅ Project existence verified!")
        else:
            print("❌ Project existence check failed")
            return False
        
        # 4. DELETE - Remove the project (using database session directly)
        print("\n4️⃣ DELETE: Removing the project...")
        try:
            with unified_db_manager.get_session() as session:
                from database.repository.project_repository import ProjectRepository
                repo = ProjectRepository(session)
                
                # Delete the project
                deleted = repo.delete_project(project_id)
                if deleted:
                    print("✅ Project deleted successfully!")
                else:
                    print("❌ Failed to delete project")
                    return False
        except Exception as e:
            print(f"❌ Error during deletion: {e}")
            return False
        
        # 5. VERIFY DELETION - Check project no longer exists
        print("\n5️⃣ VERIFY DELETION: Confirming project is gone...")
        exists_after_delete = project_service.project_exists(user_id, project_id)
        
        if not exists_after_delete:
            print("✅ Project deletion confirmed!")
        else:
            print("❌ Project still exists after deletion")
            return False
        
        print("\n🎉 All CRUD operations completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_health():
    """Test database connectivity and health"""
    print("\n🏥 Testing Database Health...")
    
    try:
        from database.db_manager import unified_db_manager
        
        health_result = unified_db_manager.health_check()
        
        print(f"📊 Health Check Results:")
        for key, value in health_result.items():
            status_icon = "✅" if value else "❌"
            print(f"   {status_icon} {key}: {value}")
        
        return health_result.get("database_available", False)
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

if __name__ == '__main__':
    print("🚀 Starting Simple PostgreSQL CRUD Test")
    print("=" * 50)
    
    # First, test database health
    health_ok = test_database_health()
    
    if not health_ok:
        print("\n❌ Database health check failed. Please ensure PostgreSQL is running.")
        print("💡 To start PostgreSQL locally:")
        print("   docker run -d --name postgres-test -p 5433:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=kondo postgres:15")
        sys.exit(1)
    
    # If health check passes, run CRUD tests
    success = test_simple_crud()
    
    if success:
        print("\n🎊 All tests passed! PostgreSQL integration is working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed. Check the output above for details.")
        sys.exit(1)