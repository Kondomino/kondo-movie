# ADR-001: Video Asset Naming Conventions

## Status
Accepted

## Date
2024-12-19

## Context
The Editora v2 platform handles multiple types of video-related assets throughout the movie creation pipeline. As we expand from image-only workflows to support video uploads and processing, we need clear, consistent naming conventions to avoid confusion between different asset types and their storage locations.

Currently, there is inconsistency in how video assets are referenced in code, storage paths, and API responses, which can lead to bugs and maintenance issues.

## Decision
We establish the following naming conventions for video-related assets:

### Asset Types

#### 1. **Videos** (Raw User Uploads)
- **Definition**: Original, unprocessed video files uploaded directly by users
- **Purpose**: Source material for scene detection and movie generation
- **Characteristics**:
  - Uploaded via `/upload-video` endpoint
  - Stored in original format and quality
  - May contain multiple scenes/segments
  - Used as input for scene extraction pipeline

#### 2. **Scene Clips**
- **Definition**: Processed video segments extracted from raw videos through automated scene detection
- **Purpose**: Individual scenes ready for classification and movie composition
- **Characteristics**:
  - Generated automatically from raw videos
  - Shorter duration (typically 2-8 seconds)
  - Optimized for movie templates
  - Classified by content type (interior, exterior, etc.)
  - Have associated keyframes and metadata

### Storage Path Conventions

#### Videos (Raw Uploads)
```
gs://{user-bucket}/{user_id}/{project_id}/videos/{video_filename}
```
- Example: `gs://editora-v2-users/user-123/project-456/videos/house_tour.mp4`

#### Scene Clips
```
gs://{user-bucket}/{user_id}/{project_id}/scene_clips/{scene_id}.mp4
```
- Example: `gs://editora-v2-users/user-123/project-456/scene_clips/scene_001.mp4`

#### Scene Clip Keyframes
```
gs://{user-bucket}/{user_id}/{project_id}/keyframes/{scene_id}/keyframe_{position}.jpg
```
- Example: `gs://editora-v2-users/user-123/project-456/keyframes/scene_001/keyframe_1.jpg`

### API and Code Conventions

#### Variable Naming
- Raw uploads: `videos`, `uploaded_videos`, `source_videos`
- Processed clips: `scene_clips`, `classified_clips`
- Combined references: `video_media`, `media_assets`

#### Database Fields
- **Firestore Collections/Documents**:
  - `media_inventory.videos` - Raw video metadata
  - `media_inventory.scene_clips` - Scene clip metadata
  - `video_classification` - Classification results for scene clips

#### API Endpoints and Models
- `/upload-video` - Upload raw videos
- `/project-videos/{project_id}` - Get project videos (with lazy-loaded scene clips)
- Models: `UploadedVideo`, `SceneClip`, `ClassifiedSceneClip`

### File Naming Patterns

#### Videos
- Format: `{original_filename}` or `video_{timestamp}.{ext}`
- Extensions: `.mp4`, `.mov`, `.m4v`, `.webm`

#### Scene Clips
- Format: `scene_{sequential_id}.mp4`
- Sequential ID: Zero-padded 3-digit number (001, 002, etc.)

#### Keyframes
- Format: `keyframe_{position}.jpg`
- Position: 0 (start), 1 (middle), 2 (end)

## Rationale

1. **Clarity**: Distinguishes between user uploads and processed assets
2. **Consistency**: Uniform naming across storage, APIs, and code
3. **Scalability**: Supports future asset types (thumbnails, transcriptions, etc.)
4. **Debugging**: Easier to trace assets through the pipeline
5. **Storage Organization**: Logical folder structure for different asset types

## Consequences

### Positive
- Clear separation of concerns between raw and processed assets
- Easier debugging and troubleshooting
- Consistent developer experience
- Better storage organization and management

### Negative
- Requires updating existing inconsistent code
- May need data migration for existing projects
- Additional complexity in storage path management

## Implementation Notes

### Immediate Actions Required
1. Update `StorageManager` methods to use consistent path conventions
2. Fix path inconsistencies in scene clip storage/retrieval
3. Update API documentation to reflect naming conventions
4. Add validation to ensure path consistency

### Migration Strategy
- Existing projects with video assets may need path migration
- Implement backward compatibility during transition period
- Add logging to track path usage during migration

## Related ADRs
- Future ADR on video processing pipeline architecture
- Future ADR on media classification strategy

---

**Decision made by**: Development Team  
**Stakeholders**: Backend Engineers, Frontend Engineers, DevOps  
**Review Date**: 2025-01-19 (1 month from decision)
