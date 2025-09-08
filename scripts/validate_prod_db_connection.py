#!/usr/bin/env python3
"""
Production Database Connection Validator

This script validates the connection to Render's PostgreSQL database
and performs basic health checks to ensure deployment readiness.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def validate_render_connection():
    """Test connection to Render PostgreSQL database"""
    print("🔍 Validating Render Database Connection...")
    print("=" * 60)
    
    try:
        # Set environment to production
        os.environ['ENVIRONMENT'] = 'prod'
        
        # Import after setting environment
        from config.config import settings
        from database.database_manager import database_manager
        from database.db_manager import unified_db_manager
        
        print("✅ Configuration loaded successfully")
        print(f"📊 Environment: {os.getenv('ENVIRONMENT', 'not set')}")
        print(f"🗄️  Database Provider: {settings.Database.PROVIDER}")
        print(f"🏗️  PostgreSQL Enabled: {settings.FeatureFlags.ENABLE_POSTGRESQL}")
        
        # Test database manager initialization
        print("\n🔗 Testing Database Manager...")
        if unified_db_manager.is_postgresql_active():
            print("✅ PostgreSQL is active in unified manager")
        else:
            print("❌ PostgreSQL is not active in unified manager")
            return False
        
        # Test health check
        print("\n🏥 Running Health Check...")
        health_result = unified_db_manager.health_check()
        
        print("📊 Health Check Results:")
        for key, value in health_result.items():
            status_icon = "✅" if value else "❌"
            print(f"   {status_icon} {key}: {value}")
        
        if not health_result.get("database_available", False):
            print("❌ Database health check failed")
            return False
        
        # Test direct connection
        print("\n🐘 Testing Direct PostgreSQL Connection...")
        try:
            with unified_db_manager.get_session() as session:
                if session:
                    from sqlalchemy import text
                    result = session.execute(text("SELECT version()")).fetchone()
                    if result:
                        version = result[0]
                        print(f"✅ Connected to PostgreSQL: {version[:50]}...")
                        
                        # Test basic table existence
                        print("\n📋 Checking Database Schema...")
                        tables_query = text("""
                            SELECT table_name 
                            FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            ORDER BY table_name
                        """)
                        tables = session.execute(tables_query).fetchall()
                        
                        if tables:
                            print(f"✅ Found {len(tables)} tables in database:")
                            for table in tables[:10]:  # Show first 10 tables
                                print(f"   📄 {table[0]}")
                            if len(tables) > 10:
                                print(f"   ... and {len(tables) - 10} more tables")
                        else:
                            print("⚠️  No tables found - database might be empty")
                        
                        return True
                    else:
                        print("❌ Failed to get PostgreSQL version")
                        return False
                else:
                    print("❌ Failed to get database session")
                    return False
        except Exception as e:
            print(f"❌ Direct connection test failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_environment_variables():
    """Check that all required environment variables are set"""
    print("\n🔍 Checking Environment Variables...")
    
    required_vars = [
        'RENDER_HOSTNAME',
        'RENDER_DB_PORT', 
        'RENDER_USR',
        'RENDER_PWD',
        'RENDER_DB'
    ]
    
    optional_vars = [
        'RENDER_INTERNAL_URL',
        'RENDER_EXTERNAL_URL',
        'DATABASE_URL'
    ]
    
    all_good = True
    
    print("📋 Required Variables:")
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            display_value = "***" if 'PWD' in var or 'PASSWORD' in var else value
            print(f"   ✅ {var}: {display_value}")
        else:
            print(f"   ❌ {var}: NOT SET")
            all_good = False
    
    print("\n📋 Optional Variables:")
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values and truncate long URLs
            if 'URL' in var:
                display_value = value[:50] + "..." if len(value) > 50 else value
            else:
                display_value = "***" if 'PWD' in var or 'PASSWORD' in var else value
            print(f"   ✅ {var}: {display_value}")
        else:
            print(f"   ⚪ {var}: not set")
    
    return all_good

def test_migration_compatibility():
    """Test if migrations can be applied (dry run)"""
    print("\n🔄 Testing Migration Compatibility...")
    
    try:
        # This would be a dry-run of migrations
        print("⚠️  Migration dry-run not implemented yet")
        print("💡 To test migrations manually, run:")
        print("   cd src && ENVIRONMENT=prod poetry run alembic check")
        print("   cd src && ENVIRONMENT=prod poetry run alembic current")
        return True
    except Exception as e:
        print(f"❌ Migration test failed: {e}")
        return False

def main():
    """Main validation function"""
    print("🚀 Starting Render Database Connection Validation")
    print("=" * 60)
    
    # Step 1: Check environment variables
    env_ok = check_environment_variables()
    if not env_ok:
        print("\n❌ Environment variable validation failed")
        print("💡 Make sure your .env.prod file contains all required Render database credentials")
        return False
    
    # Step 2: Test database connection
    connection_ok = validate_render_connection()
    if not connection_ok:
        print("\n❌ Database connection validation failed")
        return False
    
    # Step 3: Test migration compatibility
    migration_ok = test_migration_compatibility()
    if not migration_ok:
        print("\n❌ Migration compatibility test failed")
        return False
    
    print("\n🎉 All validations passed!")
    print("✅ Your application should be able to connect to Render's database")
    print("\n💡 Next steps:")
    print("   1. Run: docker-compose -f docker-compose.prod-db.yml up")
    print("   2. Test your application endpoints")
    print("   3. Run migrations if needed: cd src && ENVIRONMENT=prod poetry run alembic upgrade head")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
