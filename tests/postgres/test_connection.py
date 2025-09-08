"""
PostgreSQL Connection Test

Quick test to verify database connection and configuration.
Run with: cd tests/postgres && python test_connection.py
"""

import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from sqlalchemy import text


def test_connection():
    """Test basic database connection"""
    print("🔍 Testing PostgreSQL Connection...")
    
    try:
        # Debug environment variables first
        print(f"🔍 Environment variables:")
        print(f"   ENVIRONMENT: {os.getenv('ENVIRONMENT', 'dev')}")
        for key, value in os.environ.items():
            if key.startswith('DB_'):
                if 'PASSWORD' in key:
                    print(f"   {key}: ***")
                else:
                    print(f"   {key}: {value}")
        
        # Import configuration first
        from config.config import settings
        
        print(f"📋 Database Provider: {settings.Database.PROVIDER}")
        print(f"📋 Database Enabled: {settings.FeatureFlags.ENABLE_DATABASE}")
        print(f"📋 PostgreSQL Enabled: {settings.FeatureFlags.ENABLE_POSTGRESQL}")
        print(f"📋 Environment: {os.getenv('ENVIRONMENT', 'dev')}")
        print(f"📋 Config PostgreSQL DEV settings:")
        print(f"   HOST: {settings.PostgreSQL.DEV.HOST}")
        print(f"   PORT: {settings.PostgreSQL.DEV.PORT}")
        print(f"   DATABASE: {settings.PostgreSQL.DEV.DATABASE}")
        print(f"   SSL_REQUIRED: {settings.PostgreSQL.DEV.SSL_REQUIRED}")
        
        # Test unified database manager
        from database.db_manager import unified_db_manager
        
        print("\n🏥 Testing Database Health...")
        health = unified_db_manager.health_check()
        
        print(f"Provider: {health.get('provider')}")
        print(f"Status: {health.get('status')}")
        print(f"Message: {health.get('message')}")
        print(f"PostgreSQL Enabled: {health.get('postgresql_enabled')}")
        print(f"Database Enabled: {health.get('database_enabled')}")
        
        if health.get('status') == 'healthy':
            print("✅ Database connection is healthy!")
        else:
            print("❌ Database connection is not healthy!")
            return False
        
        # Test database manager directly if PostgreSQL is active
        if unified_db_manager.is_postgresql_active():
            print("\n🐘 Testing PostgreSQL Direct Connection...")
            from database.database_manager import database_manager
            
            with database_manager.get_session() as session:
                if session:
                    # Test a simple query
                    result = session.execute(text("SELECT version()")).fetchone()
                    print(f"✅ PostgreSQL Version: {result[0][:50]}...")
                    
                    # Test table existence
                    result = session.execute(text("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public'
                        ORDER BY table_name
                    """)).fetchall()
                    
                    if result:
                        print(f"✅ Found {len(result)} tables:")
                        for table in result:
                            print(f"   - {table[0]}")
                    else:
                        print("⚠️  No tables found - run migrations first:")
                        print("   cd src && ENVIRONMENT=dev poetry run alembic upgrade head")
                else:
                    print("❌ Failed to get PostgreSQL session")
                    return False
        else:
            print("⚠️  PostgreSQL not active - using Firestore")
            firestore_client = unified_db_manager.get_firestore_client()
            if firestore_client:
                print("✅ Firestore client available")
            else:
                print("❌ No Firestore client available")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        import traceback
        print(f"Stack trace: {traceback.format_exc()}")
        return False


def main():
    """Main function"""
    print("=" * 60)
    print("PostgreSQL Connection Test")
    print("=" * 60)
    
    success = test_connection()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 CONNECTION TEST PASSED!")
        print("✅ Your database connection is working correctly.")
        print("\nNext steps:")
        print("1. Run migrations: cd src && ENVIRONMENT=dev poetry run alembic upgrade head")
        print("2. Run CRUD test: python test_simple_crud.py")
    else:
        print("❌ CONNECTION TEST FAILED!")
        print("🔧 Please check your database configuration.")
        print("\nTroubleshooting:")
        print("1. Ensure PostgreSQL is running: docker ps")
        print("2. Check environment variables in .env file")
        print("3. Verify config.yaml database settings")
    print("=" * 60)
    
    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)
