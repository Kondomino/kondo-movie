# Digital Ocean Spaces Storage Migration Guide

This guide explains how to migrate from Google Cloud Storage to Digital Ocean Spaces using the new unified storage system.

## Overview

We've implemented a new unified storage system that can seamlessly switch between Google Cloud Storage and Digital Ocean Spaces based on configuration. The system maintains backward compatibility while providing the flexibility to use either storage provider.

## Configuration

### Environment Variables

Add these environment variables to your `.env` file:

```bash
# Digital Ocean Spaces Configuration
DIGITAL_OCEAN_STORAGE_KEY_ID=your_spaces_key_id
DIGITAL_OCEAN_STORAGE_SECRET=your_spaces_secret_key
DIGITAL_OCEAN_ORIGIN_ENDPOINT=https://nyc3.digitaloceanspaces.com
DIGITAL_OCEAN_CDN_ENDPOINT=https://your-cdn-endpoint.com
```

### Feature Flag

The system uses a feature flag to enable Digital Ocean storage:

```yaml
# config.yaml
FeatureFlags:
  ENABLE_DIGITAL_OCEAN_STORAGE: true  # Set to true to enable
```

### Storage Provider

Configure which storage provider to use:

```yaml
# config.yaml
Storage:
  PROVIDER: "DigitalOcean"  # Options: "GCP", "DigitalOcean"
```

## Code Migration

### Option 1: Use the Unified Storage Manager (Recommended)

Replace imports and usage:

```python
# OLD - Direct GCP usage
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath

storage_manager = StorageManager()
cloud_path = CloudPath(bucket_id="my-bucket", path=Path("my/path"))

# NEW - Unified storage manager
from storage_manager import storage_manager

# The storage_manager automatically uses the configured provider
# All methods work the same way regardless of provider
```

### Option 2: Minimal Code Changes

For files that extensively use the old GCP storage, you can make minimal changes:

```python
# OLD
from gcp.storage import StorageManager, cloud_storage_client

# NEW - Just change the import
from storage_manager import storage_manager as StorageManager, cloud_storage_client
```

## Migration Examples

### Example 1: Image Classification Manager

**Before:**
```python
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath

class ImageClassificationManager:
    def some_method(self):
        storage_manager = StorageManager()
        cloud_path = CloudPath(
            bucket_id=settings.GCP.Storage.PROPERTIES_BUCKET,
            path=Path(f'{property_id}/Images')
        )
        StorageManager.save_blob(source_file, cloud_path)
```

**After:**
```python
from storage_manager import storage_manager

class ImageClassificationManager:
    def some_method(self):
        buckets = storage_manager.get_buckets()
        storage_manager.save_blob(
            source_file=source_file,
            bucket=buckets['properties'],
            key=f'{property_id}/Images/image.jpg'
        )
```

### Example 2: Video Storage

**Before:**
```python
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath

def upload_video(user_id, project_id, video_file):
    cloud_path = CloudPath(
        bucket_id=settings.GCP.Storage.USER_BUCKET,
        path=Path(f'{user_id}/{project_id}/videos/{video_file.name}')
    )
    StorageManager.save_blob(video_file, cloud_path)
    return cloud_path.full_path()
```

**After:**
```python
from storage_manager import storage_manager

def upload_video(user_id, project_id, video_file):
    buckets = storage_manager.get_buckets()
    storage_manager.save_blob(
        source_file=video_file,
        bucket=buckets['users'],
        key=f'{user_id}/{project_id}/videos/{video_file.name}'
    )
    
    # Generate storage URL based on provider
    if storage_manager.get_provider_type() == "DigitalOcean":
        return f"s3://{buckets['users']}/{user_id}/{project_id}/videos/{video_file.name}"
    else:
        return f"gs://{buckets['users']}/{user_id}/{project_id}/videos/{video_file.name}"
```

## Testing

### 1. Run the Test Script

```bash
cd /path/to/kondo-movie
python test_do_storage.py
```

This script will:
- Verify environment variables are set
- Test Digital Ocean Spaces connectivity
- Test basic file operations
- Verify the unified storage manager

### 2. Manual Testing

```python
# Test the unified storage manager
from storage_manager import storage_manager

# Check current provider
print(f"Using provider: {storage_manager.get_provider_type()}")
print(f"Buckets: {storage_manager.get_buckets()}")

# Test file operations
from pathlib import Path
import tempfile

# Create test file
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
    f.write("Test content")
    test_file = Path(f.name)

# Upload
buckets = storage_manager.get_buckets()
storage_manager.save_blob(test_file, buckets['users'], 'test/example.txt')

# Generate signed URL
signed_url = storage_manager.generate_signed_url_for_view(buckets['users'], 'test/example.txt')
print(f"Signed URL: {signed_url}")
```

## Rollback Strategy

If you need to rollback to Google Cloud Storage:

1. **Change configuration:**
   ```yaml
   Storage:
     PROVIDER: "GCP"
   
   FeatureFlags:
     ENABLE_DIGITAL_OCEAN_STORAGE: false
   ```

2. **Restart the application** - the unified storage manager will automatically switch back to GCP

3. **No code changes required** - the unified interface works with both providers

## Bucket Mapping

| Purpose | GCP Bucket | Digital Ocean Bucket |
|---------|------------|---------------------|
| Properties | `editora-v2-properties` | `kondo-properties` |
| Templates | `editora-v2-templates` | `kondo-templates` |
| Users | `editora-v2-users` | `kondo-users` |

## URL Formats

| Provider | URL Format | Example |
|----------|------------|---------|
| GCP | `gs://bucket/path` | `gs://editora-v2-users/user123/project456/image.jpg` |
| Digital Ocean | `s3://bucket/path` | `s3://kondo-users/user123/project456/image.jpg` |

## Benefits of the New System

1. **Cost Savings**: Digital Ocean Spaces is typically 40-60% cheaper than Google Cloud Storage
2. **Built-in CDN**: Digital Ocean includes CDN at no extra cost
3. **S3 Compatibility**: Uses the widely-supported S3 API
4. **Seamless Migration**: Switch providers without code changes
5. **Rollback Safety**: Easy rollback to GCP if needed

## Common Issues

### 1. Missing Environment Variables
**Error**: `Missing Digital Ocean Spaces credentials`
**Solution**: Ensure all four environment variables are set in your `.env` file

### 2. Bucket Access Issues
**Error**: `Access Denied` or `NoSuchBucket`
**Solution**: 
- Verify your Digital Ocean Spaces credentials
- Ensure the buckets exist in your Digital Ocean account
- Check bucket permissions

### 3. Import Errors
**Error**: `ModuleNotFoundError: No module named 'boto3'`
**Solution**: Install dependencies: `poetry install`

### 4. Configuration Issues
**Error**: `AttributeError: 'AppConfig' object has no attribute 'DigitalOcean'`
**Solution**: Ensure your `config.yaml` has the new Digital Ocean configuration section

## Support

If you encounter issues during migration:

1. Run the test script: `python test_do_storage.py`
2. Check the logs for detailed error messages
3. Verify your Digital Ocean Spaces configuration
4. Test with a simple file upload/download first

The unified storage system is designed to be a drop-in replacement that maintains full compatibility while providing the flexibility to use either storage provider.
