#!/usr/bin/env python3

import argparse
from pathlib import Path
import logging

from utils.audio_utils import normalize_audio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SOUNDTRACK_DIR = Path('playground/samples/soundtrack')
NORMALIZED_DIR = SOUNDTRACK_DIR / 'normalized'

def normalize_tracks(track_name: str = None):
    """
    Normalize audio tracks in the soundtrack directory.
    
    Args:
        track_name: Name of specific track to normalize. If None, normalizes all tracks.
    """
    # Create normalized directory if it doesn't exist
    NORMALIZED_DIR.mkdir(exist_ok=True)
    
    # Get list of tracks to process
    if track_name and track_name.lower() != 'all':
        tracks = [SOUNDTRACK_DIR / track_name]
        if not tracks[0].exists():
            raise FileNotFoundError(f"Track not found: {track_name}")
    else:
        # Get all audio files
        tracks = list(SOUNDTRACK_DIR.glob('*.mp3')) + list(SOUNDTRACK_DIR.glob('*.wav'))
        # Exclude files in normalized directory
        tracks = [t for t in tracks if 'normalized' not in str(t)]
    
    if not tracks:
        logger.warning("No tracks found to normalize")
        return
        
    for track in tracks:
        try:
            output_path = NORMALIZED_DIR / track.name
            logger.info(f"Normalizing {track.name}...")
            
            normalize_audio(
                input_path=track,
                output_path=output_path
            )
            
            logger.info(f" Normalized {track.name} → {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to normalize {track.name}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Normalize soundtrack audio files')
    parser.add_argument('--track', type=str, default='all',
                       help='Name of track to normalize (e.g. background.mp3). Use "all" for all tracks')
    
    args = parser.parse_args()
    normalize_tracks(args.track)

if __name__ == '__main__':
    main()