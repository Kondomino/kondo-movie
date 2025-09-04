#!/usr/bin/env python3
"""
Google Video Intelligence Raw Analysis Runner

Simple script to run the raw Google Video Intelligence API analysis
to see exactly what labels Google returns for our test videos.

Usage:
    python3 run_raw_analysis.py
    python3 run_raw_analysis.py --video julie_indoor_outdoor
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_raw_analysis(video_key: str = "julie_indoor_outdoor", verbose: bool = True):
    """
    Run the raw Google Video Intelligence analysis
    
    Args:
        video_key: Key for the video to test
        verbose: Whether to show verbose output
    """
    
    # Construct pytest command
    test_file = "tests/video-intelligence/test_google_video_intelligence_raw.py"
    test_function = f"test_google_video_intelligence_raw_labels[{video_key}]"
    
    cmd = [
        "poetry", "run", "pytest",
        f"{test_file}::{test_function}",
        "-v" if verbose else "",
        "-s",  # Don't capture output so we can see the analysis
        "--tb=short"  # Shorter traceback format
    ]
    
    # Remove empty strings
    cmd = [c for c in cmd if c]
    
    print(f"🏷️  Running Google Video Intelligence Raw Analysis")
    print(f"📹 Video: {video_key}")
    print(f"🔧 Command: {' '.join(cmd)}")
    print("=" * 70)
    
    try:
        # Run the test from the project root
        project_root = Path(__file__).parent.parent.parent
        result = subprocess.run(cmd, cwd=project_root, capture_output=False)
        
        if result.returncode == 0:
            print("\n" + "=" * 70)
            print("✅ Raw analysis completed successfully!")
            print("📊 Check the generated report above for Google API labels")
            print("💾 Detailed JSON results saved in tests/video-intelligence/")
        else:
            print("\n" + "=" * 70)
            print("⚠️  Analysis completed with issues - check output above")
            print("📝 Issues are valuable for API debugging")
            
    except Exception as e:
        print(f"\n❌ Error running raw analysis: {e}")
        return False
    
    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run Google Video Intelligence raw analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_raw_analysis.py
  python3 run_raw_analysis.py --video julie_indoor_outdoor
  python3 run_raw_analysis.py --video julie_indoor_outdoor --quiet
        """
    )
    
    parser.add_argument(
        "--video", "-v",
        default="julie_indoor_outdoor",
        help="Video key to analyze (default: julie_indoor_outdoor)"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce verbose output"
    )
    
    args = parser.parse_args()
    
    # Run the raw analysis
    success = run_raw_analysis(
        video_key=args.video,
        verbose=not args.quiet
    )
    
    if success:
        print("\n🎯 Raw analysis completed!")
        print("📈 Use the Google API baseline to understand ADR-002 processing")
    else:
        print("\n❌ Raw analysis failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
