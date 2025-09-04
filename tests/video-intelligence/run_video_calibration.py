#!/usr/bin/env python3
"""
Video Classification Calibration Runner

Simple script to run the video classification calibration test
and generate comprehensive analysis reports.

Usage:
    python3 run_video_calibration.py
    python3 run_video_calibration.py --video julie_indoor_outdoor
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_calibration_test(video_key: str = "julie_indoor_outdoor", verbose: bool = True):
    """
    Run the video classification calibration test
    
    Args:
        video_key: Key for the video to test (from TEST_VIDEOS config)
        verbose: Whether to show verbose output
    """
    
    # Construct pytest command
    test_file = "tests/video-intelligence/test_video_classification_calibration.py"
    test_function = f"test_calibrate_video_classification[{video_key}]"
    
    cmd = [
        "poetry", "run", "pytest",
        f"{test_file}::{test_function}",
        "-v" if verbose else "",
        "-s",  # Don't capture output so we can see the report
        "--tb=short"  # Shorter traceback format
    ]
    
    # Remove empty strings
    cmd = [c for c in cmd if c]
    
    print(f"🎬 Running Video Classification Calibration Test")
    print(f"📹 Video: {video_key}")
    print(f"🔧 Command: {' '.join(cmd)}")
    print("=" * 60)
    
    try:
        # Run the test from the project root (two levels up from this script)
        project_root = Path(__file__).parent.parent.parent
        result = subprocess.run(cmd, cwd=project_root, capture_output=False)
        
        if result.returncode == 0:
            print("\n" + "=" * 60)
            print("✅ Calibration test completed successfully!")
            print("📊 Check the generated report above for detailed analysis")
            print("💾 Detailed JSON results saved in tests/video-intelligence/")
        else:
            print("\n" + "=" * 60)
            print("⚠️  Test completed with issues - check output above")
            print("📝 Issues are valuable for algorithm calibration")
            
    except Exception as e:
        print(f"\n❌ Error running calibration test: {e}")
        return False
    
    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run video classification calibration test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_video_calibration.py
  python3 run_video_calibration.py --video julie_indoor_outdoor
  python3 run_video_calibration.py --video julie_indoor_outdoor --quiet
        """
    )
    
    parser.add_argument(
        "--video", "-v",
        default="julie_indoor_outdoor",
        help="Video key to test (default: julie_indoor_outdoor)"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce verbose output"
    )
    
    args = parser.parse_args()
    
    # Run the calibration test
    success = run_calibration_test(
        video_key=args.video,
        verbose=not args.quiet
    )
    
    if success:
        print("\n🎯 Calibration test completed!")
        print("📈 Use the analysis results to tune algorithm parameters")
    else:
        print("\n❌ Calibration test failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
