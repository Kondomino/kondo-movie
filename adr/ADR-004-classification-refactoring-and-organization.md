# ADR-004: Classification Service Refactoring and Organization

## Status
Accepted

## Context
The classification module had grown organically with unclear separation between image and video classification, unused legacy code, and poor file organization. This created maintenance challenges and made it difficult to understand the actual classification flow.

## Decision
Restructure the classification module with clear separation of concerns and remove dead code:

### File Organization
```
src/classification/
├── image_classification_manager.py    # Image classification (Google Vision API)
├── video_classification_manager.py    # Video classification (ADR-002 implementation)
├── unified_classification_manager.py  # Main orchestrator
├── media_detector.py                  # Media type detection
├── types/
│   └── media_models.py               # Shared data models
├── storage/
│   └── video_scene_buckets.py        # Video storage models
├── unused/                           # Dead code (archived)
└── legacy/                          # Deprecated code (archived)
```

### Key Changes
1. **Renamed**: `ClassificationManager` → `ImageClassificationManager`
   - Clarifies that this service handles only image classification
   - Updated all 7 import references across the codebase

2. **Moved**: `media_models.py` → `types/media_models.py`
   - Better organization of shared type definitions
   - Updated all 5 import references

3. **Archived Dead Code**:
   - `scene_analyzer.py` → `unused/` (never imported, replaced by Google Video Intelligence)
   - `keyframe_extractor.py` → `unused/` (never imported, functionality moved to VideoClassificationManager)

4. **Clear Separation**:
   - `ImageClassificationManager`: Images only (Google Vision API)
   - `VideoClassificationManager`: Videos only (ADR-002 hybrid approach)
   - `UnifiedClassificationManager`: Orchestrates both services

## Consequences

### Positive
- **Clear Responsibility**: Each manager has a single, well-defined purpose
- **Maintainable**: Easier to understand and modify classification logic
- **Clean Codebase**: Removed 670+ lines of unused code
- **Better Organization**: Logical file structure with types separated

### Neutral
- **Import Updates**: Required updating imports across 12 files (one-time cost)
- **Class Renaming**: `ClassificationManager` → `ImageClassificationManager` (breaking change contained within project)

### Risk Mitigation
- All existing functionality preserved
- No changes to external APIs or database schemas
- Gradual migration path available if needed

## Implementation Notes
- Entry point remains: `new-media-uploaded` → `ProjectManager.media_updated()` → `UnifiedClassificationManager`
- Image classification flow: `ImageClassificationManager` (Google Vision API)
- Video classification flow: `VideoClassificationManager` (ADR-002: Video Intelligence + Vision API hybrid)
- Dead code archived (not deleted) for potential future reference

## Related
- Builds on ADR-002 (Google Video Intelligence Integration)
- Prepares for enhanced scene detection improvements
- Enables future consolidation of classification approaches

---
*Last Updated: 2025-01-02*  
*Status: Implemented and Deployed*
