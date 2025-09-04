# Purge Scripts

This folder contains scripts to purge (delete) properties and storage objects from the system.

## Scripts Overview

### 1. `purge_today_properties.py` (Main Script)
**Combined script that can handle both Firestore and Cloud Storage operations.**

**Usage:**
```bash
# List today's properties (safe, read-only)
docker exec -it editora-v2-movie-maker python tests/purge/purge_today_properties.py --action list

# Delete only Firestore documents
docker exec -it editora-v2-movie-maker python tests/purge/purge_today_properties.py --action delete-firestore --confirm

# Delete only Cloud Storage objects
docker exec -it editora-v2-movie-maker python tests/purge/purge_today_properties.py --action delete-storage --confirm

# Delete both Firestore AND Cloud Storage (recommended)
docker exec -it editora-v2-movie-maker python tests/purge/purge_today_properties.py --action delete-all --confirm
```

### 2. `delete_today_storage.py`
**Standalone script to delete only Cloud Storage objects created today.**

**Usage:**
```bash
docker exec -it editora-v2-movie-maker python tests/purge/delete_today_storage.py
```

### 3. `list_today_storage_properties.py`
**Standalone script to list Cloud Storage objects created today (read-only).**

**Usage:**
```bash
docker exec -it editora-v2-movie-maker python tests/purge/list_today_storage_properties.py
```

### 4. `delete_today_properties.py` (Legacy)
**Original script with Firestore and Cloud Storage functionality.**

**Usage:**
```bash
# List today's properties
docker exec -it editora-v2-movie-maker python tests/purge/delete_today_properties.py --action list

# Delete all (Firestore + Cloud Storage)
docker exec -it editora-v2-movie-maker python tests/purge/delete_today_properties.py --action delete-all --confirm
```

## When to Use

- **Testing**: When you want to test property extraction with fresh data
- **Debugging**: When you need to clear cached properties to test fixes
- **Cleanup**: When you want to remove test properties from the system

## Safety Features

- **Safe by default**: Scripts default to `--action list` (read-only)
- **Confirmation required**: You must use `--confirm` flag for deletion
- **Detailed logging**: Shows each operation with success/failure status
- **Error handling**: Continues processing even if individual items fail

## Examples

### Clear all today's data for testing:
```bash
docker exec -it editora-v2-movie-maker python tests/purge/purge_today_properties.py --action delete-all --confirm
```

### Just list what would be deleted:
```bash
docker exec -it editora-v2-movie-maker python tests/purge/purge_today_properties.py --action list
```

### Delete only Cloud Storage (if Firestore was already cleared):
```bash
docker exec -it editora-v2-movie-maker python tests/purge/purge_today_properties.py --action delete-storage --confirm
``` 