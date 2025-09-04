from pathlib import Path

from logger import logger
from movie_maker.edl_model import EDL

class EDLValidator():
    def __init__(self):
        pass
        
    def to_models(self, edl_dir:Path)->list[EDL]:
        edl_models = []
        try:
            # Ensure the directory exists
            if not edl_dir.is_dir():
                raise NotADirectoryError(f"The path {edl_dir} is not a directory.")
            
            # Iterate over all .json files in the directory
            for json_file in edl_dir.glob("*.json"):
                edl_models.append(self.to_model(edl_file_path=json_file))
                
            return edl_models
        
        except Exception as e:
            logger.exception(e)
            return None
    
    def to_model(self, edl_file_path:Path)->EDL:
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