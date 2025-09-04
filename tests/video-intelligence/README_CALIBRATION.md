# Video Classification Calibration Test

## Purpose
This calibration test is designed to **observe and analyze** the current ADR-002 video classification algorithm outputs without enforcing strict validation criteria. The goal is to capture comprehensive data for **algorithm tuning and calibration**.

## Key Features

### 🎯 **Non-Blocking Analysis**
- Test **never fails** based on classification quality
- Captures all data even when results are suboptimal
- Focuses on **observation** rather than validation

### 📊 **Comprehensive Reporting**
- Human-readable analysis reports
- Detailed scene-by-scene breakdown
- Label frequency analysis
- Confidence distribution analysis
- Classification source tracking (Video Intelligence vs Vision API vs Hybrid)

### 🔧 **Easy Video Switching**
- Simple configuration for testing multiple videos
- Parameterized test structure
- Easy to add new test videos

## Usage

### Quick Start
```bash
# Run with default video (julie_01_indoors_and_outdoors.MOV)
python run_video_calibration.py

# Or use pytest directly
pytest tests/video-intelligence/test_video_classification_calibration.py -v -s
```

### Advanced Usage
```bash
# Test specific video
python run_video_calibration.py --video julie_indoor_outdoor

# Quiet mode (less verbose)
python run_video_calibration.py --quiet

# Run with pytest for more control
pytest tests/video-intelligence/test_video_classification_calibration.py::test_calibrate_video_classification[julie_indoor_outdoor] -v -s
```

## Test Configuration

### Adding New Videos
Edit `TEST_VIDEOS` in `test_video_classification_calibration.py`:

```python
TEST_VIDEOS = {
    "julie_indoor_outdoor": {
        "path": "tests/properties_medias/videos/julie_01_indoors_and_outdoors.MOV",
        "description": "Multi-room indoor/outdoor property tour by Julie",
        "expected_scenes": ["kitchen", "living room", "outdoor", "bedroom"],
        "notes": "Real estate property tour with multiple indoor and outdoor spaces"
    },
    "your_new_video": {
        "path": "tests/properties_medias/videos/your_video.mp4",
        "description": "Description of your video",
        "expected_scenes": ["kitchen", "bathroom"],
        "notes": "Additional notes"
    }
}
```

### Test Parameters
- **user_id**: `calibration-test-user`
- **project_id**: `calibration-test-{timestamp}` (unique per run)
- **cleanup**: Automatic cleanup of GCS and Firestore artifacts

## Output Analysis

### Human-Readable Report
The test generates a comprehensive report including:

```
🎬 VIDEO CLASSIFICATION CALIBRATION REPORT
═══════════════════════════════════════════

📹 Video: julie_01_indoors_and_outdoors.MOV
📝 Description: Multi-room indoor/outdoor property tour by Julie
⏱️  Processing Time: 42.3 seconds
💰 Estimated Cost: $0.014

🔍 API USAGE:
✅ Google Video Intelligence API: SUCCESS
✅ Google Vision API: SUCCESS (8 keyframes processed)

📊 SCENE DETECTION RESULTS:
Total Scenes Detected: 7 scenes
Scene Categories: Kitchen, Living Room, Outdoor, Bedroom, Bathroom

🏠 DETAILED SCENE BREAKDOWN:
Scene 1: KITCHEN (00:00 - 00:15)
├── 🎯 Confidence: 89%
├── 📍 Scene ID: scene_001
├── 🏷️  Video Intelligence: kitchen, countertop, appliance
├── 🏷️  Vision API: kitchen, refrigerator, cabinet
└── 🔄 Source: Hybrid Classification

📈 ALGORITHM PERFORMANCE ANALYSIS:
Expected Categories: kitchen, living room, outdoor, bedroom
Categories Matched: kitchen, living room, outdoor
Categories Missed: bedroom
Match Rate: 75%

💡 CALIBRATION RECOMMENDATIONS:
• Consider increasing confidence thresholds for generic labels
• Algorithm may need tuning - low match rate with expected categories
```

### JSON Results File
Detailed results are saved to:
```
tests/video-intelligence/calibration_results_{video_key}_{timestamp}.json
```

This file contains:
- Complete scene details with all labels and confidence scores
- Label frequency analysis
- Confidence distribution statistics
- Classification source breakdown
- Algorithm performance metrics
- Calibration insights and recommendations

## Analysis Categories

### 📊 Scene Statistics
- Total scenes detected
- Categories found
- Scenes per category distribution

### 🏷️ Label Analysis
- All Video Intelligence labels detected
- All Vision API labels detected
- Label frequency across scenes
- Generic vs specific label ratios

### 🎯 Confidence Distribution
- Average confidence scores
- High/medium/low confidence scene counts
- Confidence by category breakdown

### 🔬 Classification Sources
- Video Intelligence only scenes
- Vision API only scenes  
- Hybrid classification scenes
- Source distribution analysis

### 📈 Algorithm Performance
- Expected vs actual categories
- Match rate calculation
- Missing and unexpected categories
- Quality score assessment

## Calibration Insights

The test provides specific recommendations for algorithm tuning:

### Label Quality Assessment
- **Quality Score**: Ratio of specific to generic labels
- **Generic/Specific Ratio**: Balance of meaningful vs noise labels
- **Recommendations**: Threshold adjustments based on label quality

### Performance Tuning
- **Confidence Thresholds**: Suggestions for optimal confidence levels
- **Scene Detection**: Recommendations for improving scene count
- **Category Matching**: Analysis of expected vs detected categories

## Integration with ADR-002

This test validates the complete ADR-002 pipeline:

1. **Google Video Intelligence API** with optimized configuration
2. **Intelligent Label Filtering** with priority system
3. **Time-Window Scene Consolidation**
4. **Precision Keyframe Extraction** at scene midpoints
5. **Google Vision API Enhancement** on keyframes
6. **Hybrid Classification Rules** with exact match priority

## Best Practices

### For Algorithm Calibration
1. **Run multiple videos** to get comprehensive data
2. **Analyze label frequency** to identify noise patterns
3. **Review confidence distributions** to optimize thresholds
4. **Check classification sources** to balance API usage
5. **Monitor processing costs** for budget optimization

### For Continuous Improvement
1. **Regular calibration runs** with new video content
2. **Compare results** across different video types
3. **Track performance metrics** over time
4. **Adjust thresholds** based on calibration insights
5. **Document changes** and their impact on results

## Troubleshooting

### Common Issues
- **Video not found**: Ensure video exists in `tests/properties_medias/videos/`
- **GCS upload fails**: Check Google Cloud credentials and permissions
- **API errors**: Verify Video Intelligence and Vision API are enabled
- **No scenes detected**: May indicate algorithm needs tuning (not a test failure)

### Debug Information
The test captures extensive debug information even on failures:
- API call details and responses
- Processing pipeline steps
- Error messages and stack traces
- Partial results when available

All debug information is valuable for algorithm improvement and should be analyzed rather than ignored.
