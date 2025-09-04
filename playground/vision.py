import os
from tempfile import TemporaryDirectory, NamedTemporaryFile
from pathlib import Path
from enum import Enum
from rich import print

import argparse
import time

from config.config import settings
from gcp.storage import StorageManager, CloudPath
from gcp.db import db_client
from classification.classification_manager import ClassificationManager
from classification.classification_model import *

class PathType(Enum):
    LOCAL_FILE = "Local File"
    LOCAL_DIR = "Local Directory"
    GS_FILE = "Google Storage File"
    GS_FOLDER = "Google Storage Folder"
    
def classify_path(path: str) -> PathType:
    if path.startswith("gs://"):
        # Google Storage paths
        stripped_path = path[5:]
        last_segment = stripped_path.strip('/').split('/')[-1]
        if '.' in last_segment:
            return PathType.GS_FILE
        else:
            return PathType.GS_FOLDER
    else:
        # Local paths
        last_segment = os.path.basename(path)
        if '.' in last_segment:
            return PathType.LOCAL_FILE
        else:
            return PathType.LOCAL_DIR

def main():
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Process images either from a single file or from a folder with a specified number of clips.")

    # Create a mutually exclusive group to ensure user chooses either file or directory mode, not both
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--file", type=str, help="Path to a single image file")
    group.add_argument("-d", "--dir", type=str, help="Path to an image folder")

    parser.add_argument("-c", "--clips", type=int, help="Number of clips (required if using directory mode)")

    args = parser.parse_args()

    # Validate conditions after parsing
    if args.file and (args.dir or args.clips):
        parser.error("You cannot specify --file together with --dir or --clips.")

    if args.dir and args.clips is None:
        parser.error("When using --dir, you must also specify --clips.")
    
    mgr = ClassificationManager()
    
    if args.dir:
        selected_images = None
        path_type = classify_path(args.dir)
        start_time = time.perf_counter()
        if path_type == PathType.GS_FOLDER:
            with TemporaryDirectory() as image_dir:
                StorageManager().load_blobs(
                    cloud_path=CloudPath.from_path(args.dir),
                    dest_dir=image_dir
                )
                all_files = [str(file) for file in Path(image_dir).rglob('*') if file.is_file()]
                image_buckets = mgr.run_classification_for_files(image_file_paths=all_files)
                selected_images = mgr.run_selection(buckets=image_buckets, num_clips=args.clips, verbose=True)
        else:
            all_files = [str(file) for file in Path(args.dir).rglob('*') if file.is_file()]
            image_buckets = mgr.run_classification_for_files(image_file_paths=all_files)
            selected_images = mgr.run_selection(buckets=image_buckets, num_clips=args.clips, verbose=True)
            
        end_time = time.perf_counter()
        elapsed = end_time - start_time
        print(f"Processing took {elapsed:.2f} seconds.")
        print(f"SELECTED IMAGES\n{selected_images}")    
    
    if args.file:
        image_info = None
        path_type = classify_path(args.file)
        if path_type == PathType.GS_FILE:
            with NamedTemporaryFile() as image_file:
                image_file_path = image_file.name
                
                StorageManager().load_blob(
                    cloud_path=CloudPath.from_path(args.file),
                    dest_file=Path(image_file_path)
                )
                labeled_image = mgr.label_image(image_file_path=image_file_path)
                categorized_images = mgr.categorize_images(labeled_images=[labeled_image])
                image_info = categorized_images[0]
        else:
            labeled_image = mgr.label_image(image_file_path=args.file)
            categorized_images = mgr.categorize_images(labeled_images=[labeled_image])
            image_info = categorized_images[0]
        print(f"IMAGE INFO:\n{image_info.model_dump_json(indent=2)}")
            
            
if __name__ == '__main__':
    main()
            
            
    