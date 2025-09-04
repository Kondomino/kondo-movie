from moviepy import ImageClip, ColorClip
from gcp.storage import StorageManager, CloudPath
from pathlib import Path
from config.config import settings
from logger import logger
from movie_maker.edl_model import Clip, ClipTypeEnum, Duration
from movie_maker.effects import Effects
from movie_maker.edl_manager import EDLUtils
from movie_maker.movie_model import MovieModel
from tempfile import NamedTemporaryFile

class AgentLogoManager():
    def __init__(self, resolution:tuple, fps:int, user_id:str):
        self.resolution = resolution
        self.fps = fps
        self.user_id = user_id
        
    def _get_logo_path(self, orientation:MovieModel.Configuration.Orientation) -> str:
        """Get the logo path from GCP bucket based on orientation"""
        orientation_str = "landscape" if orientation == MovieModel.Configuration.Orientation.Landscape else "portrait"
        logo_path = f"{self.user_id}/logos/agent_white.png"
        bucket_id = settings.GCP.Storage.USER_BUCKET
        
        print(f"LOGO 🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳")
        print(f"orientation: {orientation}")
        print(f"orientation_str: {orientation_str}")
        print(f"self.user_id: {self.user_id}")
        print(f"🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳🥳")

        # Get the image from GCP bucket
        storage_manager = StorageManager()
        cloud_path = CloudPath(bucket_id=bucket_id, path=Path(logo_path))

        print(f"cloud_path: {cloud_path}")
        
        # Download to a temporary file
        with NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
            StorageManager.load_blob(cloud_path=cloud_path, dest_file=Path(temp_file.name))
            return temp_file.name
        
    def generate_agent_logo(self, clip_start_time:float, edl_clip:Clip, orientation:MovieModel.Configuration.Orientation)->tuple[list, float]:
        agent_logo_clips = []
        clip_duration = EDLUtils.duration_to_seconds(duration=edl_clip.duration, fps=self.fps)
        
        RESOLUTION = self.resolution
        
        # Step 1 - Add pre-transition frame
        if edl_clip.transition_in and edl_clip.transition_in.transition_frame == True:
            black_frame, clip_start_time = Effects.black_frame(
                fps=self.fps, 
                resolution=RESOLUTION, 
                start_time=clip_start_time
            )
            agent_logo_clips.append(black_frame)
            
        # Step 2 - Add background clip
        background_clip = ColorClip(
            size=RESOLUTION,
            color=settings.MovieMaker.EndTitles.General.BG_COLOR
        ).with_start(clip_start_time).with_duration(clip_duration)
        background_clip = Effects.apply_transition(clip=background_clip, edl_clip=edl_clip, fps=self.fps)
        
        # Step 3 - Add agent logo
        try:
            logo_path = self._get_logo_path(orientation)
            logo_clip = ImageClip(logo_path)
            
            # Calculate logo position and size
            # Keep aspect ratio and fit within margins
            logo_width, logo_height = logo_clip.size
            aspect_ratio = logo_width / logo_height
            
            # Calculate max dimensions based on resolution and margins
            max_width = RESOLUTION[0] - 2*settings.MovieMaker.EndTitles.Geometry.Landscape.H_MARGIN \
                if RESOLUTION[0] > RESOLUTION[1] \
                    else RESOLUTION[0] - 2*settings.MovieMaker.EndTitles.Geometry.Portrait.H_MARGIN
            max_height = RESOLUTION[1] - 2*settings.MovieMaker.EndTitles.Geometry.Landscape.V_MARGIN \
                if RESOLUTION[0] > RESOLUTION[1] \
                    else RESOLUTION[1] - 2*settings.MovieMaker.EndTitles.Geometry.Portrait.V_MARGIN
            
            # Calculate new dimensions maintaining aspect ratio
            if logo_width / max_width > logo_height / max_height:
                new_width = max_width
                new_height = new_width / aspect_ratio
            else:
                new_height = max_height
                new_width = new_height * aspect_ratio
                
            # Resize logo
            logo_clip = logo_clip.resized(height=new_height, width=new_width)
            
            # Center logo
            x_pos = (RESOLUTION[0] - new_width) / 2
            y_pos = (RESOLUTION[1] - new_height) / 2
            
            # Set clip properties
            logo_clip = logo_clip.with_start(clip_start_time).with_duration(clip_duration
            ).with_position((x_pos, y_pos))
            
            # Add transitions if necessary
            logo_clip = Effects.apply_transition(clip=logo_clip, edl_clip=edl_clip, fps=self.fps)
            
            # Step 4 - Append background & logo clips
            agent_logo_clips.append(background_clip)
            agent_logo_clips.append(logo_clip)
            
        except Exception as e:
            logger.error(f"Failed to load agent logo: {e}")
            # If logo loading fails, just use the background
            agent_logo_clips.append(background_clip)
        
        # Step 5 - Update start time
        clip_start_time += clip_duration
            
        # Step 6 - Add post-transition frame
        if edl_clip.transition_out and edl_clip.transition_out.transition_frame == True:
            black_frame, clip_start_time = Effects.black_frame(
                fps=self.fps, 
                resolution=RESOLUTION, 
                start_time=clip_start_time
            )
            agent_logo_clips.append(black_frame)
        
        return agent_logo_clips, clip_start_time 