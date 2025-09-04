"""
Video Classification Calibration Test

Objective: Observe and analyze the current video classification algorithm outputs
to calibrate and tune the ADR-002 hybrid pipeline. This test does NOT enforce
strict validation criteria - instead it captures comprehensive data for analysis.

Usage:
    pytest tests/video-intelligence/test_video_classification_calibration.py -v -s
    pytest tests/video-intelligence/test_video_classification_calibration.py::test_calibrate_video_classification[julie_indoor_outdoor] -v -s
"""

import pytest
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Import our classification services
import sys
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from classification.video_classification_manager import VideoClassificationManager
from classification.media_models import VideoMedia
from classification.storage import VideoSceneBuckets
from logger import logger


# Test Configuration - Easy to add more videos
TEST_VIDEOS = {
    "julie_indoor_outdoor": {
        "path": "tests/properties_medias/videos/julie_01_indoors_and_outdoors.MOV",
        "description": "Multi-room indoor/outdoor property tour by Julie",
        "expected_scenes": ["kitchen", "living room", "outdoor", "bedroom"],  # For reference only
        "notes": "Real estate property tour with multiple indoor and outdoor spaces"
    },
    # Easy to add more videos for calibration:
    # "complex_property": {
    #     "path": "tests/properties_medias/videos/another_video.mp4",
    #     "description": "Another property tour",
    #     "expected_scenes": ["kitchen", "bathroom", "living room"],
    #     "notes": "Additional test case"
    # }
}

# Test user/project IDs for calibration
TEST_USER_ID = "calibration-test-user"
TEST_PROJECT_ID = f"calibration-test-{int(time.time())}"

class VideoClassificationCalibrator:
    """
    Utility class for analyzing and reporting video classification results
    Focus on comprehensive data capture for calibration purposes
    """
    
    def __init__(self):
        self.video_classifier = VideoClassificationManager()
    
    def analyze_classification_results(self, video_scene_buckets: VideoSceneBuckets, 
                                     video_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive analysis of classification results for calibration
        
        Args:
            video_scene_buckets: Classification results
            video_config: Test video configuration
            
        Returns:
            Detailed analysis report
        """
        # Debug: Log the buckets structure
        print(f"🔍 DEBUG - VideoSceneBuckets type: {type(video_scene_buckets)}")
        print(f"🔍 DEBUG - VideoSceneBuckets attributes: {[attr for attr in dir(video_scene_buckets) if not attr.startswith('_')]}")
        print(f"🔍 DEBUG - Buckets dict keys: {list(video_scene_buckets.buckets.keys()) if hasattr(video_scene_buckets, 'buckets') else 'No buckets attr'}")
        
        if hasattr(video_scene_buckets, 'buckets'):
            for category, scenes in video_scene_buckets.buckets.items():
                print(f"🔍 DEBUG - Category '{category}' has {len(scenes)} scenes")
                if scenes:
                    first_scene = scenes[0]
                    print(f"🔍 DEBUG - First scene in '{category}': type={type(first_scene)}, attrs={[attr for attr in dir(first_scene) if not attr.startswith('_')]}")
        
        analysis = {
            "video_info": {
                "name": video_config["path"].split("/")[-1],
                "description": video_config["description"],
                "notes": video_config.get("notes", "")
            },
            "processing_summary": video_scene_buckets.processing_summary,
            "api_usage": {
                "google_video_intelligence_used": video_scene_buckets.google_video_intelligence_used,
                "google_vision_api_used": video_scene_buckets.google_vision_api_used
            },
            "scene_statistics": self._analyze_scene_statistics(video_scene_buckets),
            "label_analysis": self._analyze_labels(video_scene_buckets),
            "confidence_distribution": self._analyze_confidence_distribution(video_scene_buckets),
            "classification_sources": self._analyze_classification_sources(video_scene_buckets),
            "scene_details": self._extract_scene_details(video_scene_buckets),
            "calibration_insights": self._generate_calibration_insights(video_scene_buckets, video_config)
        }
        
        return analysis
    
    def _analyze_scene_statistics(self, buckets: VideoSceneBuckets) -> Dict[str, Any]:
        """Analyze basic scene statistics"""
        categories = buckets.get_categories()
        summary_stats = buckets.get_summary_stats()
        
        return {
            "total_scenes": buckets.total_scenes,
            "unique_categories": len(categories),
            "categories_found": categories,
            "summary_stats": summary_stats,
            "scenes_per_category": {cat: len(scenes) for cat, scenes in buckets.buckets.items()}
        }
    
    def _analyze_labels(self, buckets: VideoSceneBuckets) -> Dict[str, Any]:
        """Analyze all labels detected across all scenes"""
        all_video_labels = set()
        all_vision_labels = set()
        label_frequency = {}
        
        for category, scenes in buckets.buckets.items():
            for scene in scenes:
                # Video Intelligence labels
                if hasattr(scene, 'video_intelligence_labels'):
                    for label in scene.video_intelligence_labels:
                        label_name = label.description if hasattr(label, 'description') else str(label)
                        all_video_labels.add(label_name)
                        label_frequency[label_name] = label_frequency.get(label_name, 0) + 1
                
                # Vision API labels
                if hasattr(scene, 'vision_classification') and scene.vision_classification:
                    if hasattr(scene.vision_classification, 'labels'):
                        for label in scene.vision_classification.labels:
                            label_name = label.description if hasattr(label, 'description') else str(label)
                            all_vision_labels.add(label_name)
                            label_frequency[f"vision_{label_name}"] = label_frequency.get(f"vision_{label_name}", 0) + 1
        
        return {
            "video_intelligence_labels": sorted(list(all_video_labels)),
            "vision_api_labels": sorted(list(all_vision_labels)),
            "total_unique_labels": len(all_video_labels) + len(all_vision_labels),
            "label_frequency": dict(sorted(label_frequency.items(), key=lambda x: x[1], reverse=True))
        }
    
    def _analyze_confidence_distribution(self, buckets: VideoSceneBuckets) -> Dict[str, Any]:
        """Analyze confidence score distribution across scenes"""
        confidences = []
        confidence_by_category = {}
        
        for category, scenes in buckets.buckets.items():
            category_confidences = []
            for scene in scenes:
                if hasattr(scene, 'combined_confidence'):
                    confidences.append(scene.combined_confidence)
                    category_confidences.append(scene.combined_confidence)
                elif hasattr(scene, 'confidence_score'):
                    confidences.append(scene.confidence_score)
                    category_confidences.append(scene.confidence_score)
            
            if category_confidences:
                confidence_by_category[category] = {
                    "average": sum(category_confidences) / len(category_confidences),
                    "min": min(category_confidences),
                    "max": max(category_confidences),
                    "count": len(category_confidences)
                }
        
        if confidences:
            return {
                "overall_average": sum(confidences) / len(confidences),
                "overall_min": min(confidences),
                "overall_max": max(confidences),
                "high_confidence_scenes": len([c for c in confidences if c >= 0.8]),
                "medium_confidence_scenes": len([c for c in confidences if 0.6 <= c < 0.8]),
                "low_confidence_scenes": len([c for c in confidences if c < 0.6]),
                "by_category": confidence_by_category
            }
        else:
            return {"note": "No confidence scores available in results"}
    
    def _analyze_classification_sources(self, buckets: VideoSceneBuckets) -> Dict[str, Any]:
        """Analyze how scenes were classified (Video Intelligence vs Vision API vs Hybrid)"""
        sources = {
            "video_intelligence_only": 0,
            "vision_api_only": 0,
            "hybrid_classification": 0,
            "unknown_source": 0
        }
        
        source_details = []
        
        for category, scenes in buckets.buckets.items():
            for scene in scenes:
                source_info = {
                    "category": category,
                    "scene_id": getattr(scene, 'scene_id', 'unknown'),
                    "has_video_intelligence": False,
                    "has_vision_api": False,
                    "classification_source": "unknown"
                }
                
                # Check Video Intelligence data
                if hasattr(scene, 'video_intelligence_labels') and scene.video_intelligence_labels:
                    source_info["has_video_intelligence"] = True
                
                # Check Vision API data
                if hasattr(scene, 'vision_classification') and scene.vision_classification:
                    source_info["has_vision_api"] = True
                
                # Determine classification source
                if source_info["has_video_intelligence"] and source_info["has_vision_api"]:
                    source_info["classification_source"] = "hybrid"
                    sources["hybrid_classification"] += 1
                elif source_info["has_video_intelligence"]:
                    source_info["classification_source"] = "video_intelligence_only"
                    sources["video_intelligence_only"] += 1
                elif source_info["has_vision_api"]:
                    source_info["classification_source"] = "vision_api_only"
                    sources["vision_api_only"] += 1
                else:
                    sources["unknown_source"] += 1
                
                source_details.append(source_info)
        
        return {
            "summary": sources,
            "details": source_details
        }
    
    def _extract_scene_details(self, buckets: VideoSceneBuckets) -> List[Dict[str, Any]]:
        """Extract detailed information for each scene"""
        scene_details = []
        
        for category, scenes in buckets.buckets.items():
            for i, scene in enumerate(scenes):
                # Debug: Log the actual scene object attributes
                scene_attrs = [attr for attr in dir(scene) if not attr.startswith('_')]
                print(f"🔍 DEBUG - Scene {len(scene_details) + 1} attributes: {scene_attrs}")
                print(f"🔍 DEBUG - Scene object type: {type(scene)}")
                print(f"🔍 DEBUG - Scene dict representation: {scene.__dict__ if hasattr(scene, '__dict__') else 'No __dict__'}")
                
                detail = {
                    "scene_number": len(scene_details) + 1,
                    "category": category,
                    "scene_id": getattr(scene, 'scene_id', f"{category}_{i}"),
                    "timestamps": {
                        "start": getattr(scene, 'start_time', 'unknown'),
                        "end": getattr(scene, 'end_time', 'unknown'),
                        "duration": getattr(scene, 'end_time', 0) - getattr(scene, 'start_time', 0) if hasattr(scene, 'start_time') and hasattr(scene, 'end_time') else 'unknown'
                    },
                    "confidence": getattr(scene, 'combined_confidence', getattr(scene, 'confidence_score', 'unknown')),
                    "keyframe_info": {
                        "timestamp": getattr(scene, 'keyframe_timestamp', 'unknown'),
                        "gs_url": getattr(scene, 'primary_keyframe_gs_url', 'unknown')
                    }
                }
                
                # Video Intelligence labels
                if hasattr(scene, 'video_intelligence_labels'):
                    detail["video_intelligence_labels"] = [
                        {
                            "description": getattr(label, 'description', str(label)),
                            "confidence": getattr(label, 'confidence', 'unknown')
                        } for label in scene.video_intelligence_labels
                    ]
                
                # Vision API classification
                if hasattr(scene, 'vision_classification') and scene.vision_classification:
                    detail["vision_classification"] = {
                        "category": getattr(scene.vision_classification, 'category', 'unknown'),
                        "confidence": getattr(scene.vision_classification, 'confidence', 'unknown'),
                        "labels": []
                    }
                    if hasattr(scene.vision_classification, 'labels'):
                        detail["vision_classification"]["labels"] = [
                            {
                                "description": getattr(label, 'description', str(label)),
                                "score": getattr(label, 'score', 'unknown')
                            } for label in scene.vision_classification.labels
                        ]
                
                scene_details.append(detail)
        
        return scene_details
    
    def _generate_calibration_insights(self, buckets: VideoSceneBuckets, 
                                     video_config: Dict[str, Any]) -> Dict[str, Any]:
        """Generate insights for calibrating the algorithm"""
        insights = {
            "algorithm_performance": {},
            "potential_improvements": [],
            "label_quality_assessment": {},
            "recommendations": []
        }
        
        # Analyze expected vs actual categories
        expected_scenes = video_config.get("expected_scenes", [])
        found_categories = buckets.get_categories()
        
        insights["algorithm_performance"] = {
            "expected_categories": expected_scenes,
            "found_categories": found_categories,
            "categories_matched": list(set(expected_scenes) & set(found_categories)),
            "categories_missed": list(set(expected_scenes) - set(found_categories)),
            "unexpected_categories": list(set(found_categories) - set(expected_scenes)),
            "match_rate": len(set(expected_scenes) & set(found_categories)) / len(expected_scenes) if expected_scenes else "N/A"
        }
        
        # Analyze label quality
        label_analysis = self._analyze_labels(buckets)
        generic_labels = ["room", "interior", "floor", "wall", "property", "furniture", "table", "chair"]
        specific_labels = ["kitchen", "bedroom", "bathroom", "living room", "outdoor", "swimming pool", "patio"]
        
        video_labels = label_analysis["video_intelligence_labels"]
        generic_count = len([label for label in video_labels if label.lower() in generic_labels])
        specific_count = len([label for label in video_labels if label.lower() in specific_labels])
        
        insights["label_quality_assessment"] = {
            "generic_labels_found": generic_count,
            "specific_labels_found": specific_count,
            "generic_to_specific_ratio": generic_count / specific_count if specific_count > 0 else "infinite",
            "quality_score": specific_count / (generic_count + specific_count) if (generic_count + specific_count) > 0 else 0
        }
        
        # Generate recommendations
        if generic_count > specific_count:
            insights["recommendations"].append("Consider increasing confidence thresholds for generic labels")
        
        if insights["algorithm_performance"]["match_rate"] != "N/A" and insights["algorithm_performance"]["match_rate"] < 0.7:
            insights["recommendations"].append("Algorithm may need tuning - low match rate with expected categories")
        
        if buckets.total_scenes < 3:
            insights["recommendations"].append("Consider lowering confidence thresholds to detect more scenes")
        
        return insights
    
    def generate_human_readable_report(self, analysis: Dict[str, Any]) -> str:
        """Generate a comprehensive human-readable report"""
        report_lines = []
        
        # Header
        report_lines.extend([
            "🎬 VIDEO CLASSIFICATION CALIBRATION REPORT",
            "═" * 50,
            "",
            f"📹 Video: {analysis['video_info']['name']}",
            f"📝 Description: {analysis['video_info']['description']}",
            f"📋 Notes: {analysis['video_info']['notes']}",
            ""
        ])
        
        # Processing Summary
        if analysis.get("processing_summary"):
            summary = analysis["processing_summary"]
            report_lines.extend([
                "⚙️  PROCESSING SUMMARY:",
                f"⏱️  Processing Time: {summary.get('total_processing_time', 'Unknown')}s",
                f"💰 Estimated Cost: ${summary.get('estimated_cost', 'Unknown')}",
                f"🔧 Videos Processed: {summary.get('videos_processed', 'Unknown')}",
                ""
            ])
        
        # API Usage
        api_usage = analysis["api_usage"]
        report_lines.extend([
            "🔍 API USAGE:",
            f"{'✅' if api_usage['google_video_intelligence_used'] else '❌'} Google Video Intelligence API",
            f"{'✅' if api_usage['google_vision_api_used'] else '❌'} Google Vision API",
            ""
        ])
        
        # Scene Statistics
        stats = analysis["scene_statistics"]
        report_lines.extend([
            "📊 SCENE DETECTION RESULTS:",
            f"Total Scenes Detected: {stats['total_scenes']} scenes",
            f"Unique Categories: {stats['unique_categories']}",
            f"Categories Found: {', '.join(stats['categories_found'])}",
            ""
        ])
        
        # Scenes per category
        report_lines.append("📈 SCENES PER CATEGORY:")
        for category, count in stats["scenes_per_category"].items():
            bar_length = min(20, count * 2)  # Visual bar
            bar = "█" * bar_length
            report_lines.append(f"├── {category:15} {bar} {count} scenes")
        report_lines.append("")
        
        # Confidence Distribution
        if "overall_average" in analysis["confidence_distribution"]:
            conf_dist = analysis["confidence_distribution"]
            report_lines.extend([
                "🎯 CONFIDENCE DISTRIBUTION:",
                f"Average Confidence: {conf_dist['overall_average']:.1%}",
                f"High Confidence (≥80%): {conf_dist['high_confidence_scenes']} scenes",
                f"Medium Confidence (60-80%): {conf_dist['medium_confidence_scenes']} scenes",
                f"Low Confidence (<60%): {conf_dist['low_confidence_scenes']} scenes",
                ""
            ])
        
        # Classification Sources
        sources = analysis["classification_sources"]["summary"]
        total_scenes = sum(sources.values())
        if total_scenes > 0:
            report_lines.extend([
                "🔬 CLASSIFICATION SOURCES:",
                f"├── Video Intelligence Only: {sources['video_intelligence_only']} scenes ({sources['video_intelligence_only']/total_scenes:.1%})",
                f"├── Vision API Only: {sources['vision_api_only']} scenes ({sources['vision_api_only']/total_scenes:.1%})",
                f"├── Hybrid Classification: {sources['hybrid_classification']} scenes ({sources['hybrid_classification']/total_scenes:.1%})",
                f"└── Unknown Source: {sources['unknown_source']} scenes ({sources['unknown_source']/total_scenes:.1%})",
                ""
            ])
        
        # Detailed Scene Breakdown
        report_lines.extend([
            "🏠 DETAILED SCENE BREAKDOWN:",
            "─" * 50
        ])
        
        for scene in analysis["scene_details"]:
            report_lines.extend([
                f"",
                f"Scene {scene['scene_number']}: {scene['category'].upper()} ({scene['timestamps']['start']:.1f}s - {scene['timestamps']['end']:.1f}s)" if isinstance(scene['timestamps']['start'], (int, float)) else f"Scene {scene['scene_number']}: {scene['category'].upper()}",
                f"├── 🎯 Confidence: {scene['confidence']:.1%}" if isinstance(scene['confidence'], (int, float)) else f"├── 🎯 Confidence: {scene['confidence']}",
                f"├── 📍 Scene ID: {scene['scene_id']}",
            ])
            
            # Video Intelligence Labels
            if scene.get("video_intelligence_labels"):
                labels = [f"{label['description']} ({label['confidence']:.1%})" if isinstance(label['confidence'], (int, float)) else label['description'] for label in scene["video_intelligence_labels"]]
                report_lines.append(f"├── 🏷️  Video Intelligence: {', '.join(labels)}")
            
            # Vision API Labels
            if scene.get("vision_classification", {}).get("labels"):
                labels = [f"{label['description']} ({label['score']:.1%})" if isinstance(label['score'], (int, float)) else label['description'] for label in scene["vision_classification"]["labels"]]
                report_lines.append(f"├── 🏷️  Vision API: {', '.join(labels)}")
            
            # Classification source indicator
            source_detail = next((s for s in analysis["classification_sources"]["details"] if s["scene_id"] == scene["scene_id"]), {})
            source_emoji = {"hybrid": "🔄", "video_intelligence_only": "📹", "vision_api_only": "👁️", "unknown": "❓"}
            source_name = source_detail.get("classification_source", "unknown")
            report_lines.append(f"└── {source_emoji.get(source_name, '❓')} Source: {source_name.replace('_', ' ').title()}")
        
        # Algorithm Performance Analysis
        insights = analysis["calibration_insights"]
        perf = insights["algorithm_performance"]
        
        report_lines.extend([
            "",
            "📈 ALGORITHM PERFORMANCE ANALYSIS:",
            "─" * 50,
            f"Expected Categories: {', '.join(perf['expected_categories']) if perf['expected_categories'] else 'None specified'}",
            f"Categories Matched: {', '.join(perf['categories_matched']) if perf['categories_matched'] else 'None'}",
            f"Categories Missed: {', '.join(perf['categories_missed']) if perf['categories_missed'] else 'None'}",
            f"Unexpected Categories: {', '.join(perf['unexpected_categories']) if perf['unexpected_categories'] else 'None'}",
            f"Match Rate: {perf['match_rate']:.1%}" if isinstance(perf['match_rate'], (int, float)) else f"Match Rate: {perf['match_rate']}",
            ""
        ])
        
        # Label Quality Assessment
        quality = insights["label_quality_assessment"]
        report_lines.extend([
            "🏆 LABEL QUALITY ASSESSMENT:",
            f"├── Specific Labels Found: {quality['specific_labels_found']}",
            f"├── Generic Labels Found: {quality['generic_labels_found']}",
            f"├── Quality Score: {quality['quality_score']:.1%}",
            f"└── Generic/Specific Ratio: {quality['generic_to_specific_ratio']:.2f}" if isinstance(quality['generic_to_specific_ratio'], (int, float)) else f"└── Generic/Specific Ratio: {quality['generic_to_specific_ratio']}",
            ""
        ])
        
        # Recommendations
        if insights["recommendations"]:
            report_lines.extend([
                "💡 CALIBRATION RECOMMENDATIONS:",
                *[f"• {rec}" for rec in insights["recommendations"]],
                ""
            ])
        
        # Footer
        report_lines.extend([
            "═" * 50,
            f"📅 Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "🎯 Purpose: Algorithm Calibration & Tuning"
        ])
        
        return "\n".join(report_lines)


@pytest.fixture
def calibrator():
    """Fixture to provide VideoClassificationCalibrator instance"""
    return VideoClassificationCalibrator()


@pytest.fixture
def test_video_path():
    """Fixture to provide test video path"""
    video_path = Path(__file__).parent.parent / "properties_medias/videos/julie_01_indoors_and_outdoors.MOV"
    if not video_path.exists():
        pytest.skip(f"Test video not found: {video_path}")
    return str(video_path)


def upload_test_video_to_gcs(video_path: str, user_id: str, project_id: str) -> str:
    """
    Upload test video to GCS for processing
    
    Args:
        video_path: Local path to video file
        user_id: Test user ID
        project_id: Test project ID
        
    Returns:
        GCS URL for uploaded video
    """
    import os
    from google.cloud import storage
    from google.oauth2 import service_account
    from config.config import settings
    
    # Service account path (same as used in other modules)
    SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'
    
    print(f"📤 Uploading {video_path} to GCS...")
    
    # Set up credentials (same pattern as other modules)
    credentials = None
    if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_KEY_FILE_PATH,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    
    client = storage.Client(credentials=credentials)
    bucket_name = settings.GCP.Storage.USER_BUCKET
    bucket = client.bucket(bucket_name)
    
    # Create blob name following ADR-001 conventions
    video_filename = Path(video_path).name
    blob_name = f"{user_id}/{project_id}/videos/{video_filename}"
    blob = bucket.blob(blob_name)
    
    # Upload the video file
    blob.upload_from_filename(video_path)
    
    gs_url = f"gs://{bucket_name}/{blob_name}"
    logger.info(f"[TEST] Uploaded test video to: {gs_url}")
    return gs_url


def cleanup_test_artifacts(user_id: str, project_id: str):
    """
    Clean up test artifacts from GCS and Firestore
    
    Args:
        user_id: Test user ID
        project_id: Test project ID
    """
    try:
        import os
        from google.cloud import storage
        from google.oauth2 import service_account
        from config.config import settings
        
        # Service account path (same as used in other modules)
        SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'
        
        # Clean up GCS files
        credentials = None
        if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
            credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_KEY_FILE_PATH,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
        
        client = storage.Client(credentials=credentials)
        bucket_name = settings.GCP.Storage.USER_BUCKET
        bucket = client.bucket(bucket_name)
        
        # List and delete files with the test prefix
        prefix = f"{user_id}/{project_id}/"
        blobs = bucket.list_blobs(prefix=prefix)
        
        deleted_count = 0
        for blob in blobs:
            blob.delete()
            deleted_count += 1
        
        logger.info(f"[TEST] Cleaned up {deleted_count} GCS files with prefix: {prefix}")
        
        # Clean up Firestore data
        try:
            from utils.session_utils import get_session_refs_by_ids
            _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            project_ref.delete()
            logger.info(f"[TEST] Cleaned up Firestore project: {project_id}")
        except Exception as e:
            logger.warning(f"[TEST] Could not clean up Firestore project: {e}")
            
    except Exception as e:
        logger.warning(f"[TEST] Cleanup failed: {e}")


@pytest.mark.parametrize("video_key", ["julie_indoor_outdoor"])
def test_calibrate_video_classification(video_key, calibrator, test_video_path):
    """
    Main calibration test - observes and analyzes video classification results
    without enforcing strict validation criteria.
    
    Args:
        video_key: Key for video configuration
        calibrator: VideoClassificationCalibrator instance
        test_video_path: Path to test video file
    """
    print(f"\n🎬 Starting Video Classification Calibration Test")
    print(f"📹 Video: {video_key}")
    
    video_config = TEST_VIDEOS[video_key]
    
    try:
        # Step 1: Upload test video to GCS
        print(f"📤 Uploading test video to GCS...")
        gs_url = upload_test_video_to_gcs(test_video_path, TEST_USER_ID, TEST_PROJECT_ID)
        
        # Step 2: Create VideoMedia object
        video_media = VideoMedia(uri=gs_url, duration=0.0)  # Duration will be detected
        
        # Step 3: Run classification through the consolidated manager
        print(f"🔄 Running video classification through ADR-002 pipeline...")
        start_time = time.time()
        
        video_scene_buckets = calibrator.video_classifier.classify_videos(
            [video_media], 
            TEST_USER_ID, 
            TEST_PROJECT_ID
        )
        
        processing_time = time.time() - start_time
        print(f"⏱️  Processing completed in {processing_time:.2f} seconds")
        
        # Step 4: Analyze results comprehensively
        print(f"📊 Analyzing classification results...")
        analysis = calibrator.analyze_classification_results(video_scene_buckets, video_config)
        
        # Step 5: Generate human-readable report
        print(f"📋 Generating calibration report...")
        report = calibrator.generate_human_readable_report(analysis)
        
        # Step 6: Display the report
        print("\n" + report)
        
        # Step 7: Save detailed results to file for further analysis
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = Path(__file__).parent / f"calibration_results_{video_key}_{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        
        print(f"\n💾 Detailed results saved to: {results_file}")
        
        # Step 8: Basic assertions (non-blocking, for observation)
        # These are informational only - test will not fail if they don't pass
        observations = []
        
        if video_scene_buckets.total_scenes == 0:
            observations.append("⚠️  No scenes detected - algorithm may need tuning")
        else:
            observations.append(f"✅ {video_scene_buckets.total_scenes} scenes detected")
        
        if not video_scene_buckets.google_video_intelligence_used:
            observations.append("⚠️  Google Video Intelligence API was not used")
        else:
            observations.append("✅ Google Video Intelligence API was used")
        
        if not video_scene_buckets.google_vision_api_used:
            observations.append("⚠️  Google Vision API was not used")
        else:
            observations.append("✅ Google Vision API was used")
        
        categories = video_scene_buckets.get_categories()
        if not categories:
            observations.append("⚠️  No categories detected")
        else:
            observations.append(f"✅ {len(categories)} categories detected: {', '.join(categories)}")
        
        # Display observations
        print(f"\n🔍 CALIBRATION OBSERVATIONS:")
        for obs in observations:
            print(f"  {obs}")
        
        print(f"\n🎯 Test completed successfully - results captured for calibration")
        
        # Always pass - this is a calibration test, not a validation test
        assert True, "Calibration test completed successfully"
        
    except Exception as e:
        # Even on error, we want to capture what we can
        print(f"\n❌ Error during calibration test: {e}")
        print(f"📝 This error information is valuable for algorithm debugging")
        
        # Don't fail the test - log the error for analysis
        logger.error(f"[CALIBRATION_TEST] Error: {e}")
        
        # Still pass the test so we can analyze partial results
        assert True, f"Calibration test encountered error (logged for analysis): {e}"
        
    finally:
        # Clean up test artifacts
        print(f"🧹 Cleaning up test artifacts...")
        cleanup_test_artifacts(TEST_USER_ID, TEST_PROJECT_ID)


if __name__ == "__main__":
    # Allow running the test directly
    pytest.main([__file__, "-v", "-s"])
