from tempfile import NamedTemporaryFile
from pathlib import Path

from moviepy import ImageClip

from config.config import settings
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath

class Watermark():
    def __init__(self, resolution:tuple, duration:float):
        self.RESOLUTION = resolution
        self.duration = duration
        
    def generate_watermark_clip(self) -> ImageClip:
        storage_mgr = StorageManager()
        with NamedTemporaryFile() as watermark_file:
            bucket_id = settings.GCP.Storage.TEMPLATES_BUCKET
            path = f"{settings.MovieMaker.Watermark.STORAGE_DIR_PREFIX}/{settings.MovieMaker.Watermark.EDITORA}"
            cloud_path = CloudPath(
                bucket_id=bucket_id,
                path=Path(path)
            )
            storage_mgr.load_blob(
                cloud_path=cloud_path, 
                dest_file=Path(watermark_file.name))
            
            
            watermark = ImageClip(watermark_file.name).with_duration(self.duration)
            
            size_by_height = settings.MovieMaker.Watermark.SIZE_BY_HEIGHT_PORTRAIT \
                if self.RESOLUTION == settings.MovieMaker.Video.RESOLUTION_PORTRAIT \
                    else settings.MovieMaker.Watermark.SIZE_BY_HEIGHT_LANDSCAPE
            watermark = watermark.resized(
                height=size_by_height)

            pixel_offset_width = settings.MovieMaker.Watermark.PIXEL_OFFSET_WIDTH_PORTRAIT \
                if self.RESOLUTION == settings.MovieMaker.Video.RESOLUTION_PORTRAIT \
                    else settings.MovieMaker.Watermark.PIXEL_OFFSET_WIDTH_LANDSCAPE
            pixel_offset_height = settings.MovieMaker.Watermark.PIXEL_OFFSET_HEIGHT_PORTRAIT \
                if self.RESOLUTION == settings.MovieMaker.Video.RESOLUTION_PORTRAIT \
                    else settings.MovieMaker.Watermark.PIXEL_OFFSET_HEIGHT_LANDSCAPE
                    
            watermark_position = (
                self.RESOLUTION[0] - watermark.w - pixel_offset_width,
                self.RESOLUTION[1] - watermark.h - pixel_offset_height
            )
            watermark = watermark.with_position(
                watermark_position).with_opacity(
                    settings.MovieMaker.Watermark.OPACITY
                )
            
            return watermark