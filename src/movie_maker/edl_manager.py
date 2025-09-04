import os
from pathlib import Path
import argparse
from enum import Enum
import random
from typing import Any
from rich import print

from movie_maker.edl_model import EDL, Duration
from gcp.db import db_client
from config.config import settings
from logger import logger


class EDLManager():
    @staticmethod
    def get_collection_ref(with_title:bool)->Any:
        if with_title:
            collection_ref = db_client.collection(settings.GCP.Firestore.Templates.TEMPLATES_COLLECTION_NAME)\
                .document(settings.GCP.Firestore.Templates.WITH_TITLE_DOCUMENT_NAME)\
                    .collection(settings.GCP.Firestore.Templates.EDLS_COLLECTION_NAME)
        else:
            collection_ref = db_client.collection(settings.GCP.Firestore.Templates.TEMPLATES_COLLECTION_NAME)\
                .document(settings.GCP.Firestore.Templates.NO_TITLE_DOCUMENT_NAME)\
                    .collection(settings.GCP.Firestore.Templates.EDLS_COLLECTION_NAME)
                        
        return collection_ref
    
    @staticmethod
    def get_doc_ref(edl_id:str, with_title:bool)->Any:
        if with_title:
            doc_ref = db_client.collection(settings.GCP.Firestore.Templates.TEMPLATES_COLLECTION_NAME)\
                .document(settings.GCP.Firestore.Templates.WITH_TITLE_DOCUMENT_NAME)\
                    .collection(settings.GCP.Firestore.Templates.EDLS_COLLECTION_NAME)\
                        .document(edl_id.lower())
        else:
            doc_ref = db_client.collection(settings.GCP.Firestore.Templates.TEMPLATES_COLLECTION_NAME)\
                .document(settings.GCP.Firestore.Templates.NO_TITLE_DOCUMENT_NAME)\
                    .collection(settings.GCP.Firestore.Templates.EDLS_COLLECTION_NAME)\
                        .document(edl_id.lower())
                        
        return doc_ref
        
    @staticmethod
    def save_edl(edl:EDL, with_title:bool)->bool:
        try:
            doc_ref = EDLManager.get_doc_ref(edl_id=edl.name, with_title=with_title)
            doc = doc_ref.get()
            if doc.exists:
                logger.warning(f"EDL template '{edl.name}' already exists. Overwriting record in DB")
                
            doc_ref.set(edl.model_dump())
            logger.success(f"Saved EDL in Firestore. Name : {edl.name}")
                    
        except Exception as e:
            logger.exception(f"Failed to save EDL: {e}")
            raise e
        
    @staticmethod
    def load_edl_from_file(edl_file_path:Path):
        try:
            # Check if the file exists
            if not edl_file_path.is_file() or edl_file_path.suffix.lower() != '.json':
                error_str = f"The file {edl_file_path} does not exist or is not a JSON file"
                raise FileNotFoundError(error_str)
            
            # Read the JSON content as a string
            json_content = edl_file_path.read_text(encoding="utf-8")
            return EDL.model_validate_json(json_data=json_content)
        except Exception as e:
            logger.exception(e)
            return None
    
    @staticmethod
    def load_edl(edl_id:str, with_title:bool)->EDL:
        try:
            doc_ref = EDLManager.get_doc_ref(edl_id=edl_id, with_title=with_title)
            doc = doc_ref.get()
            if not doc.exists:
                logger.error(f"Unable to fetch EDL template '{edl_id}'")
                return None
                
            return EDL.model_validate(obj=doc.to_dict())
        except Exception as e:
            logger.exception(f"Failed to load EDL: {e}")
            raise e
            
    @staticmethod
    def load_all_edls(with_title:bool) -> list[EDL]:
        try:
            col_ref = EDLManager.get_collection_ref(with_title=with_title)
            docs = col_ref.stream()  # or col_ref.get(), both work

            all_edls: list[EDL] = []
            for doc in docs:
                if not doc.exists:
                    continue
                edl_data = doc.to_dict()
                try:
                    edl = EDL.model_validate(obj=edl_data)
                    all_edls.append(edl)
                except Exception as model_exc:
                    logger.error(f"Failed to parse EDL doc '{doc.id}' into EDL model: {model_exc}")

            return all_edls
        
        except Exception as e:
            logger.exception(f"Failed to load all EDLs: {e}")
            raise e
        
class EDLUtils():
    @staticmethod
    def duration_to_seconds(duration:Duration, fps:int) -> float:
        return round((duration.seconds + duration.frames / fps), 2)
    
    @staticmethod
    def add_clip_durations(d1:Duration, d2:Duration, fps:int) -> Duration:
        """
        Add two Duration objects taking into account frames per second (fps).

        This function sums the seconds and frames separately. If the sum of frames
        exceeds or equals the fps, the 'excess' frames are converted into seconds.
        
        :param d1: First duration
        :param d2: Second duration
        :param fps: Frames per second to determine how frames carry over into seconds
        :return: A new Duration object representing the sum
        """
        
        total_seconds = d1.seconds + d2.seconds
        total_frames = d1.frames + d2.frames

        # Carry over frames to seconds if total_frames >= fps
        if total_frames >= fps:
            extra_seconds = total_frames // fps
            total_frames = total_frames % fps
            total_seconds += extra_seconds

        return Duration(seconds=total_seconds, frames=total_frames)
    
    
def main():        
    def validate_file(edl_file_path:str):
        edl = EDLManager.load_edl_from_file(edl_file_path=edl_file_path)
        if not edl:
            logger.error(f"Could not load EDL from file : {edl_file_path}")
            return None
        
        logger.info(f"Successfully loaded EDL : {edl.name}")
        return edl
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='EDL Manager')
    edl_group = parser.add_mutually_exclusive_group(required=True)
    edl_group.add_argument('-e', '--edl', type=str, help='EDL to upload')
    edl_group.add_argument('-a', '--all', action='store_true', help='All EDLs')
    
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument('-v', '--validate', action='store_true', help='Validate')
    action_group.add_argument('-l', '--load', action='store_true', help='Load EDL from cloud')
    action_group.add_argument('-s', '--save', action='store_true', help='Save EDL onto cloud')
    
    parser.add_argument('-t', '--title', action='store_true', help='Templates w/ or w/o title clips')
    
    args = parser.parse_args()
    
    if args.title:
        template_dir = "library/templates/with_title"
    else:
        template_dir = "library/templates/no_title"
    
    try:
        if args.all:
            if args.load:
                edls = EDLManager.load_all_edls(with_title=args.title)
                print("Loaded All EDLs")
                print(edls)
            else:    
                for filename in os.listdir(template_dir):
                    if filename.endswith(".json"):
                        edl_file_path = Path(os.path.join(template_dir, filename))
                        edl = validate_file(edl_file_path=edl_file_path)
                        if args.save:
                            EDLManager.save_edl(edl=edl, with_title=args.title)
        else:
            edl_file_name = f"{args.edl}.json"
            edl_file_path = Path(os.path.join(template_dir, edl_file_name))
            if args.load:
                edl = EDLManager.load_edl(edl_id=args.edl, with_title=args.title)
                print(f"Loaded EDL: {args.edl}")
                print(edl)
            else:
                edl = validate_file(edl_file_path=edl_file_path)
                if args.save:
                    EDLManager.save_edl(edl=edl, with_title=args.title)
            
    except Exception as e:
        logger.exception(e)
        
if __name__ == '__main__':
    main()