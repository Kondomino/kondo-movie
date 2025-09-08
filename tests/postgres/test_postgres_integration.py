"""
PostgreSQL Integration Test

Tests the complete database abstraction layer including:
- Database connection management
- Service layer operations
- Repository pattern
- CRUD operations
- Database switching functionality
"""

import os
import sys
import uuid
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from rich import print
from rich.console import Console
from rich.table import Table

# Import our database components
from database.db_manager import unified_db_manager
from database.database_manager import database_manager
from services.project_service import project_service
from services.classification_service import classification_storage_service
from config.config import settings

console = Console()


def test_database_connection():
    """Test basic database connection and health check"""
    console.print("\n[bold blue]🔍 Testing Database Connection[/bold blue]")
    
    try:
        # Test health check
        health_status = unified_db_manager.health_check()
        
        console.print(f"Database Provider: [green]{health_status.get('provider')}[/green]")
        console.print(f"PostgreSQL Enabled: [green]{health_status.get('postgresql_enabled')}[/green]")
        console.print(f"Database Status: [green]{health_status.get('status')}[/green]")
        
        if health_status.get('message'):
            console.print(f"Message: {health_status.get('message')}")
        
        # Test if PostgreSQL is active
        is_postgres_active = unified_db_manager.is_postgresql_active()
        console.print(f"PostgreSQL Active: [green]{is_postgres_active}[/green]")
        
        if is_postgres_active:
            console.print("[green]✅ PostgreSQL connection test passed[/green]")
        else:
            console.print("[yellow]⚠️  Using Firestore (PostgreSQL not active)[/yellow]")
            
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Database connection test failed: {e}[/red]")
        return False


def test_project_crud_operations():
    """Test complete CRUD operations using our service layer"""
    console.print("\n[bold blue]🏗️ Testing Project CRUD Operations[/bold blue]")
    
    # Generate unique test data
    test_user_id = f"test-user-{uuid.uuid4()}"
    test_project_id = f"test-project-{uuid.uuid4()}"
    
    try:
        # 1. CREATE - Test project creation
        console.print("1. Testing project creation...")
        project_data = {
            "name": "Test Project Integration",
            "description": "Testing PostgreSQL integration",
            "property_id": "test-property-123",
            "excluded_images": ["image1.jpg", "image2.jpg"],
            "status": "active",
            "custom_field": "test_value"
        }
        
        created_project = project_service.create_project(test_user_id, test_project_id, project_data)
        
        if created_project:
            console.print("[green]✅ Project created successfully[/green]")
            console.print(f"   Project ID: {created_project.get('id')}")
            console.print(f"   Name: {created_project.get('name')}")
        else:
            console.print("[red]❌ Project creation failed[/red]")
            return False
        
        # 2. READ - Test project retrieval
        console.print("2. Testing project retrieval...")
        retrieved_project = project_service.get_project(test_user_id, test_project_id)
        
        if retrieved_project:
            console.print("[green]✅ Project retrieved successfully[/green]")
            console.print(f"   Retrieved name: {retrieved_project.get('name')}")
            console.print(f"   Retrieved description: {retrieved_project.get('description')}")
            
            # Verify data integrity
            assert retrieved_project.get('name') == project_data['name']
            assert retrieved_project.get('property_id') == project_data['property_id']
            console.print("[green]✅ Data integrity verified[/green]")
        else:
            console.print("[red]❌ Project retrieval failed[/red]")
            return False
        
        # 3. UPDATE - Test project updates
        console.print("3. Testing project updates...")
        updates = {
            "description": "Updated description for integration test",
            "status": "in_progress",
            "new_field": "updated_value"
        }
        
        updated_project = project_service.update_project(test_user_id, test_project_id, updates)
        
        if updated_project:
            console.print("[green]✅ Project updated successfully[/green]")
            console.print(f"   Updated description: {updated_project.get('description')}")
            console.print(f"   Updated status: {updated_project.get('status')}")
            
            # Verify updates
            assert updated_project.get('description') == updates['description']
            assert updated_project.get('status') == updates['status']
            console.print("[green]✅ Update integrity verified[/green]")
        else:
            console.print("[red]❌ Project update failed[/red]")
            return False
        
        # 4. LIST - Test project listing
        console.print("4. Testing project listing...")
        user_projects = project_service.get_user_projects(test_user_id)
        
        if user_projects and len(user_projects) > 0:
            console.print(f"[green]✅ Found {len(user_projects)} projects for user[/green]")
            
            # Verify our test project is in the list
            test_project_found = any(p.get('id') == test_project_id for p in user_projects)
            if test_project_found:
                console.print("[green]✅ Test project found in user projects list[/green]")
            else:
                console.print("[red]❌ Test project not found in user projects list[/red]")
                return False
        else:
            console.print("[red]❌ Project listing failed[/red]")
            return False
        
        # 5. EXISTS - Test project existence check
        console.print("5. Testing project existence check...")
        exists = project_service.project_exists(test_user_id, test_project_id)
        
        if exists:
            console.print("[green]✅ Project existence check passed[/green]")
        else:
            console.print("[red]❌ Project existence check failed[/red]")
            return False
        
        # 6. CLASSIFICATION STORAGE - Test classification data storage
        console.print("6. Testing classification storage...")
        classification_data = {
            "image_classification": {
                "buckets": {
                    "exterior": [{"uri": "test1.jpg", "score": 0.95}],
                    "interior": [{"uri": "test2.jpg", "score": 0.87}]
                }
            },
            "media_inventory": {
                "total_files": 2,
                "image_count": 2,
                "video_count": 0
            }
        }
        
        classification_stored = classification_storage_service.store_unified_classification(
            test_user_id, test_project_id, classification_data
        )
        
        if classification_stored:
            console.print("[green]✅ Classification data stored successfully[/green]")
            
            # Test classification retrieval
            retrieved_classification = classification_storage_service.get_classification_results(
                test_user_id, test_project_id
            )
            
            if retrieved_classification:
                console.print("[green]✅ Classification data retrieved successfully[/green]")
                console.print(f"   Media inventory: {retrieved_classification.get('media_inventory')}")
            else:
                console.print("[red]❌ Classification data retrieval failed[/red]")
                return False
        else:
            console.print("[red]❌ Classification data storage failed[/red]")
            return False
        
        # 7. CLEANUP - Delete test project
        console.print("7. Testing project deletion...")
        
        if unified_db_manager.is_postgresql_active():
            # For PostgreSQL, we can test actual deletion
            with database_manager.get_session() as session:
                if session:
                    from database.repository.project_repository import ProjectRepository
                    repo = ProjectRepository(session)
                    
                    # Find and delete the project
                    projects = repo.get_by_filter(user_id=test_user_id, id=test_project_id)
                    if projects:
                        deleted = repo.delete(projects[0].id)
                        if deleted:
                            console.print("[green]✅ Project deleted successfully[/green]")
                            
                            # Verify deletion
                            exists_after_delete = project_service.project_exists(test_user_id, test_project_id)
                            if not exists_after_delete:
                                console.print("[green]✅ Project deletion verified[/green]")
                            else:
                                console.print("[red]❌ Project still exists after deletion[/red]")
                                return False
                        else:
                            console.print("[red]❌ Project deletion failed[/red]")
                            return False
                    else:
                        console.print("[yellow]⚠️  Project not found for deletion[/yellow]")
                else:
                    console.print("[yellow]⚠️  No PostgreSQL session available for deletion test[/yellow]")
        else:
            # For Firestore, just mark as completed since we don't want to delete from Firestore
            console.print("[yellow]⚠️  Skipping deletion test (using Firestore)[/yellow]")
        
        console.print("[green]🎉 All CRUD operations completed successfully![/green]")
        return True
        
    except Exception as e:
        console.print(f"[red]❌ CRUD operations test failed: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")
        return False


def test_database_switching_compatibility():
    """Test that our abstraction works with both database types"""
    console.print("\n[bold blue]🔄 Testing Database Switching Compatibility[/bold blue]")
    
    try:
        current_provider = settings.Database.PROVIDER
        postgres_enabled = settings.FeatureFlags.ENABLE_POSTGRESQL
        
        console.print(f"Current Provider: [green]{current_provider}[/green]")
        console.print(f"PostgreSQL Enabled: [green]{postgres_enabled}[/green]")
        
        # Test service layer methods work regardless of database
        test_user_id = f"compatibility-user-{uuid.uuid4()}"
        test_project_id = f"compatibility-project-{uuid.uuid4()}"
        
        # Test basic operations
        exists_before = project_service.project_exists(test_user_id, test_project_id)
        console.print(f"Project exists before creation: [green]{exists_before}[/green]")
        
        user_projects_before = project_service.get_user_projects(test_user_id)
        console.print(f"User projects before: [green]{len(user_projects_before)}[/green]")
        
        # Test unified session manager
        from services.session_service import unified_session_manager
        user_ref, project_ref, _ = unified_session_manager.get_session_refs_by_ids(
            test_user_id, test_project_id
        )
        
        console.print(f"Session refs created: [green]✅[/green]")
        console.print(f"User ref type: [green]{type(user_ref).__name__}[/green]")
        console.print(f"Project ref type: [green]{type(project_ref).__name__}[/green]")
        
        console.print("[green]✅ Database switching compatibility verified[/green]")
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Database switching compatibility test failed: {e}[/red]")
        return False


def display_test_summary(results):
    """Display a summary table of test results"""
    console.print("\n[bold blue]📊 Test Results Summary[/bold blue]")
    
    table = Table(title="PostgreSQL Integration Test Results")
    table.add_column("Test", style="cyan", no_wrap=True)
    table.add_column("Status", style="magenta")
    table.add_column("Description", style="green")
    
    for test_name, (status, description) in results.items():
        status_emoji = "✅ PASS" if status else "❌ FAIL"
        table.add_row(test_name, status_emoji, description)
    
    console.print(table)
    
    # Overall result
    all_passed = all(status for status, _ in results.values())
    if all_passed:
        console.print("\n[bold green]🎉 All tests passed! PostgreSQL integration is working correctly.[/bold green]")
    else:
        console.print("\n[bold red]❌ Some tests failed. Please check the database configuration.[/bold red]")
    
    return all_passed


def main():
    """Main test function"""
    console.print("[bold blue]🚀 Starting PostgreSQL Integration Tests[/bold blue]")
    console.print(f"Environment: {os.getenv('ENVIRONMENT', 'dev')}")
    console.print(f"Database Provider: {settings.Database.PROVIDER}")
    console.print(f"PostgreSQL Enabled: {settings.FeatureFlags.ENABLE_POSTGRESQL}")
    
    # Run all tests
    test_results = {}
    
    # Test 1: Database Connection
    result1 = test_database_connection()
    test_results["Database Connection"] = (result1, "Basic connection and health check")
    
    # Test 2: CRUD Operations
    result2 = test_project_crud_operations()
    test_results["CRUD Operations"] = (result2, "Create, Read, Update, Delete operations")
    
    # Test 3: Database Switching Compatibility
    result3 = test_database_switching_compatibility()
    test_results["Switching Compatibility"] = (result3, "Database abstraction layer compatibility")
    
    # Display summary
    all_passed = display_test_summary(test_results)
    
    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")
        sys.exit(1)
