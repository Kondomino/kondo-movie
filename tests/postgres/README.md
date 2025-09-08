# PostgreSQL Integration Tests

This directory contains tests to verify the PostgreSQL database integration and abstraction layer.

## Test Files

### 1. `test_connection.py` - Basic Connection Test
Quick verification that the database connection is working.

```bash
cd tests/postgres
python test_connection.py
```

**What it tests:**
- Database configuration loading
- Health check functionality
- PostgreSQL connection (if active)
- Table existence check
- Firestore fallback (if PostgreSQL not active)

### 2. `test_simple_crud.py` - Basic CRUD Operations
Tests fundamental database operations using our service layer.

```bash
cd tests/postgres
python test_simple_crud.py
```

**What it tests:**
- CREATE: Project creation
- READ: Project retrieval
- UPDATE: Project modification
- EXISTS: Project existence check
- LIST: User projects listing
- DELETE: Project deletion (PostgreSQL only)

### 3. `test_postgres_integration.py` - Comprehensive Integration Test
Full integration test including classification storage and database switching.

```bash
cd tests/postgres
python test_postgres_integration.py
```

**What it tests:**
- Complete CRUD operations
- Classification data storage/retrieval
- Database switching compatibility
- Service layer abstraction
- Error handling and rollback

## Prerequisites

### 1. PostgreSQL Setup
```bash
# Start PostgreSQL container
docker run --name kondo-postgres \
  -e POSTGRES_DB=kondo \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 -d postgres:15
```

### 2. Environment Configuration
Create/update `.env` file with:
```bash
# PostgreSQL Development
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=kondo
ENVIRONMENT=dev
```

### 3. Database Configuration
Update `src/config/config.yaml`:
```yaml
Database:
  PROVIDER: "PostgreSQL"

FeatureFlags:
  ENABLE_DATABASE: true
  ENABLE_POSTGRESQL: true
```

### 4. Run Migrations
```bash
cd src
ENVIRONMENT=dev poetry run alembic upgrade head
```

## Running the Tests

### Quick Connection Test
```bash
cd tests/postgres
python test_connection.py
```

### Basic CRUD Test
```bash
cd tests/postgres
python test_simple_crud.py
```

### Full Integration Test
```bash
cd tests/postgres
python test_postgres_integration.py
```

## Expected Output

### Successful Connection Test
```
🔍 Testing PostgreSQL Connection...
📋 Database Provider: PostgreSQL
📋 PostgreSQL Enabled: True
✅ Database connection is healthy!
🐘 Testing PostgreSQL Direct Connection...
✅ PostgreSQL Version: PostgreSQL 15.x...
✅ Found 5 tables:
   - projects
   - project_versions
   - properties
   - sessions
   - movies
   - videos
```

### Successful CRUD Test
```
1️⃣ Testing CREATE operation...
✅ CREATE: Project created successfully

2️⃣ Testing READ operation...
✅ READ: Project retrieved successfully

3️⃣ Testing UPDATE operation...
✅ UPDATE: Project updated successfully

4️⃣ Testing EXISTS operation...
✅ EXISTS: Project existence confirmed

5️⃣ Testing LIST operation...
✅ LIST: Found 1 projects for user

6️⃣ Testing DELETE operation...
✅ DELETE: Project deleted successfully
✅ DELETE: Deletion verified

🎉 All CRUD operations completed successfully!
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   ```
   psycopg2.OperationalError: connection to server at "localhost", port 5432 failed
   ```
   - **Solution**: Start PostgreSQL container
   - **Check**: `docker ps` to verify container is running

2. **No Tables Found**
   ```
   ⚠️ No tables found - run migrations first
   ```
   - **Solution**: Run Alembic migrations
   - **Command**: `cd src && ENVIRONMENT=dev poetry run alembic upgrade head`

3. **Import Errors**
   ```
   ModuleNotFoundError: No module named 'services'
   ```
   - **Solution**: Run from correct directory
   - **Command**: `cd tests/postgres && python test_connection.py`

4. **Configuration Issues**
   ```
   Database Provider: Firestore (expected PostgreSQL)
   ```
   - **Solution**: Update `config.yaml` and `.env` files
   - **Check**: Database provider and feature flags

### Database Switching Test

To test database switching:

1. **Test with PostgreSQL:**
   ```yaml
   # config.yaml
   Database:
     PROVIDER: "PostgreSQL"
   FeatureFlags:
     ENABLE_POSTGRESQL: true
   ```

2. **Test with Firestore:**
   ```yaml
   # config.yaml
   Database:
     PROVIDER: "Firestore"
   FeatureFlags:
     ENABLE_POSTGRESQL: false
   ```

3. **Run tests with both configurations** to verify abstraction works.

## Test Results Interpretation

- ✅ **Green checkmarks**: Operations completed successfully
- ❌ **Red X marks**: Operations failed (check error messages)
- ⚠️ **Yellow warnings**: Non-critical issues or skipped operations
- 🎉 **Success message**: All tests passed

## Integration with CI/CD

These tests can be integrated into CI/CD pipelines:

```bash
#!/bin/bash
# PostgreSQL integration test script

# Start test database
docker run -d --name test-postgres -p 5432:5432 \
  -e POSTGRES_DB=kondo_test \
  -e POSTGRES_USER=test \
  -e POSTGRES_PASSWORD=test \
  postgres:15

# Wait for database to be ready
sleep 10

# Run migrations
cd src && ENVIRONMENT=dev poetry run alembic upgrade head

# Run tests
cd tests/postgres
python test_connection.py && python test_simple_crud.py

# Cleanup
docker stop test-postgres
docker rm test-postgres
```

The tests provide comprehensive verification that the PostgreSQL integration and database abstraction layer are working correctly.
