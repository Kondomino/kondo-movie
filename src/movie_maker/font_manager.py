from gcp.storage import StorageManager, CloudPath
from pathlib import Path
from config.config import settings
from logger import logger
from movie_maker.edl_model import ClipTypeEnum
from tempfile import NamedTemporaryFile
import os

class FontManager:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._font_cache = {}
        
    def _get_font_name_for_clip_type(self, clip_type: ClipTypeEnum) -> str:
        """Map clip type to font filename"""
        font_mapping = {
            ClipTypeEnum.AGENT_NAME: "AgentName.ttf",
            ClipTypeEnum.ADDRESS: "Address.ttf", 
            ClipTypeEnum.PROPERTY_LOCATION: "PropertyLocation.ttf",
            ClipTypeEnum.OCCASION_TEXT: "OccasionTitle.ttf",
            ClipTypeEnum.OCCASION_SUBTITLE: "OccasionSubtitle.ttf",
            ClipTypeEnum.TITLE: "Title.ttf",
            ClipTypeEnum.PRESENTS: "Presents.ttf",
        }
        return font_mapping.get(clip_type, "Default.ttf")
    
    def _get_default_font_for_clip_type(self, clip_type: ClipTypeEnum) -> str:
        """Get default font for each clip type"""
        default_fonts = {
            ClipTypeEnum.AGENT_NAME: settings.MovieMaker.EndTitles.Main.Font.NAME,
            ClipTypeEnum.ADDRESS: "GothamOffice-Regular.otf",
            ClipTypeEnum.PROPERTY_LOCATION: "Gotham-Light.otf", 
            ClipTypeEnum.OCCASION_TEXT: "GothamOffice-Regular.otf",
            ClipTypeEnum.OCCASION_SUBTITLE: "Gotham-Light.otf",
            ClipTypeEnum.TITLE: settings.MovieMaker.EndTitles.Main.Font.NAME,
            ClipTypeEnum.PRESENTS: settings.MovieMaker.EndTitles.Main.Font.NAME,
        }
        return default_fonts.get(clip_type, settings.MovieMaker.EndTitles.Main.Font.NAME)
    
    def get_font_path(self, clip_type: ClipTypeEnum) -> str:
        """Get font path for clip type, with fallback to default font"""
        
        # Check cache first (apply it in the future - todo)
        # if clip_type in self._font_cache:
        #     return self._font_cache[clip_type]
            
        font_filename = self._get_font_name_for_clip_type(clip_type)
        font_path = f"{self.user_id}/fonts/{font_filename}"
        print(f"font_path: {font_path}")
        bucket_id = settings.GCP.Storage.USER_BUCKET
        
        try:
            # Try to get custom font from GCP bucket
            storage_manager = StorageManager()
            cloud_path = CloudPath(bucket_id=bucket_id, path=Path(font_path))
            
            # Download to a temporary file
            with NamedTemporaryFile(delete=False, suffix='.ttf') as temp_file:
                StorageManager.load_blob(cloud_path=cloud_path, dest_file=Path(temp_file.name))
                logger.info(f"Loaded custom font for {clip_type}: {font_filename}")
                self._font_cache[clip_type] = temp_file.name
                return temp_file.name
                
        except Exception as e:
            logger.info(f"Custom font not found for {clip_type} ({font_filename}), using default: {e}")
            # Fall back to default font
            default_font = self._get_default_font_for_clip_type(clip_type)
            self._font_cache[clip_type] = default_font
            return default_font
    
    def cleanup_temp_fonts(self):
        """Clean up temporary font files"""
        for clip_type, font_path in self._font_cache.items():
            if font_path.startswith('/tmp') or font_path.startswith('/var'):
                try:
                    os.unlink(font_path)
                    logger.debug(f"Cleaned up temp font file: {font_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp font {font_path}: {e}")
        self._font_cache.clear() 