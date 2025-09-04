from PIL import Image, ImageOps
import numpy as np
import math
from typing import Any

from moviepy import Clip, ImageClip, ColorClip, vfx
from movie_maker.edl_model import Clip as EDLClip, Transition, TransitionEffectEnum
from movie_maker.edl_manager import EDLUtils
from movie_maker.movie_model import MovieModel
from PIL import Image

from config.config import settings

class Effects():
    @staticmethod
    def load_image_from_path(image_path: str)->Image:
        # Load and correct orientation using PIL
        img = Image.open(image_path)
        ImageOps.exif_transpose(img, in_place=True)
        
        return img
    
    @staticmethod
    def get_image_orientation(image_path: str)->MovieModel.Configuration.Orientation:
        img = Effects.load_image_from_path(image_path=image_path)
        width, height = img.size
        
        return \
            MovieModel.Configuration.Orientation.Portrait if width < height \
                else MovieModel.Configuration.Orientation.Landscape
    
    @staticmethod
    def gen_imageclip(image_path: str, resolution:tuple)->ImageClip:
        """
        Corrects image orientation if needed 
        Crops and resizes an ImageClip to the desired resolution without padding,
        adjusting the image as necessary to match the desired aspect ratio.

        Parameters:
            image_clip (ImageClip): The input ImageClip to be cropped and resized.
            desired_resolution (tuple): The desired output resolution (width, height).

        Returns:
            ImageClip: The cropped and resized ImageClip with the desired resolution.
        """
        RESOLUTION = resolution
        
        img = Effects.load_image_from_path(image_path=image_path)
        
        # Convert the PIL image to a NumPy array and create the ImageClip
        frame = np.array(img)
        image_clip = ImageClip(frame)
        
        # Original dimensions
        original_width, original_height = image_clip.size
        desired_width, desired_height = RESOLUTION

        # Calculate aspect ratios
        original_ratio = original_width / original_height
        desired_ratio = desired_width / desired_height

        # Determine the dimensions to crop
        if original_ratio > desired_ratio:
            # Original is wider than desired aspect ratio
            # Need to crop width
            new_width = int(original_height * desired_ratio)
            new_height = original_height
            x_center = original_width / 2
            x1 = x_center - new_width / 2
            x2 = x_center + new_width / 2
            y1 = 0
            y2 = original_height
        else:
            # Original is taller than desired aspect ratio
            # Need to crop height
            new_width = original_width
            new_height = int(original_width / desired_ratio)
            y_center = original_height / 2
            y1 = y_center - new_height / 2
            y2 = y_center + new_height / 2
            x1 = 0
            x2 = original_width

        # Crop the image
        cropped_clip = image_clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2)

        # Resize the cropped image to the desired resolution
        resized_clip = cropped_clip.resized(new_size=RESOLUTION)

        return resized_clip
    
    @staticmethod
    def zoom_in(clip:ImageClip, zoom_factor:float=settings.MovieMaker.Image.ZOOM_FACTOR)->Any:
        
        def effect(get_frame, t):
            img = Image.fromarray(get_frame(t))
            base_size = img.size
    
            new_size = [
                math.ceil(img.size[0] * (1 + (zoom_factor * t))),
                math.ceil(img.size[1] * (1 + (zoom_factor * t)))
            ]
    
            # The new dimensions must be even.
            new_size[0] = new_size[0] + (new_size[0] % 2)
            new_size[1] = new_size[1] + (new_size[1] % 2)
    
            img = img.resize(new_size, Image.LANCZOS)
    
            x = math.ceil((new_size[0] - base_size[0]) / 2)
            y = math.ceil((new_size[1] - base_size[1]) / 2)
    
            img = img.crop([
                x, y, new_size[0] - x, new_size[1] - y
            ]).resize(base_size, Image.LANCZOS)
    
            result = np.array(img)
            img.close()
    
            return result
 
        return clip.transform(effect)

    @staticmethod
    def zoom_out(clip:ImageClip, 
                  zoom_factor:float=settings.MovieMaker.Image.ZOOM_FACTOR, 
                  initial_zoom_in_ratio:float=settings.MovieMaker.Image.INITIAL_ZOOM_IN_RATIO_FOR_ZOOM_OUT)->Any:
        
        def effect(get_frame, t):
            img = Image.fromarray(get_frame(t))
            base_size = img.size
    
            # Reverse the zoom effect by starting zoomed in and zooming out
            scale_factor = initial_zoom_in_ratio - (zoom_factor * t)
            scale_factor = max(scale_factor, 0)  # Ensure scale factor doesn't go negative
    
            new_size = [
                math.ceil(base_size[0] * (1 + scale_factor)),
                math.ceil(base_size[1] * (1 + scale_factor))
            ]
    
            # The new dimensions must be even.
            new_size[0] = new_size[0] - (new_size[0] % 2)
            new_size[1] = new_size[1] - (new_size[1] % 2)
    
            img = img.resize(new_size, Image.LANCZOS)
    
            x = math.ceil((new_size[0] - base_size[0]) / 2)
            y = math.ceil((new_size[1] - base_size[1]) / 2)
    
            img = img.crop([
                x, y, new_size[0] - x, new_size[1] - y
            ])
    
            # Resize back to base size
            img = img.resize(base_size, Image.LANCZOS)
    
            result = np.array(img)
            img.close()
    
            return result
    
        return clip.transform(effect)
    
    @staticmethod
    def pan_right(clip:ImageClip, 
                  fps:int,
                  resolution:tuple,
                  pan_speed:float=settings.MovieMaker.Image.PAN_SPEED):
        def effect(get_frame, t):
            img = Image.fromarray(get_frame(t))
            base_size = img.size
    
            x1 = math.ceil(t*fps*pan_speed)
            x2 = img.size[0]-math.ceil((clip.duration-t)*fps*pan_speed)
    
            img = img.crop([
                x1, 0, x2, base_size[1]
            ])
    
            # Resize back to base size
            img = img.resize(resolution, Image.LANCZOS)
    
            result = np.array(img)
            img.close()
    
            return result
    
        return clip.transform(effect)
    
    @staticmethod
    def pan_left(clip:ImageClip, 
                   fps:int,
                   resolution:tuple,
                   pan_speed:float=settings.MovieMaker.Image.PAN_SPEED):
        def effect(get_frame, t):
            img = Image.fromarray(get_frame(t))
            base_size = img.size
    
            x1 = math.ceil((clip.duration-t)*fps*pan_speed)
            x2 = base_size[0]-math.ceil(t*fps*pan_speed)
            
            img = img.crop([
                x1, 0, x2, base_size[1]
            ])
    
            # Resize back to base size
            img = img.resize(resolution, Image.LANCZOS)
    
            result = np.array(img)
            img.close()
    
            return result
    
        return clip.transform(effect)
    
    @staticmethod
    def apply_transition(clip:Clip, edl_clip:EDLClip, fps:int)->Clip:
        
        t_in = edl_clip.transition_in
        if t_in and t_in.effect == TransitionEffectEnum.FADE:
            clip = clip.with_effects([vfx.CrossFadeIn(EDLUtils.duration_to_seconds(duration=t_in.duration, fps=fps))])
        else:
            # Assume CUT. Only FADE & CUT supported for now
            pass
        
        t_out = edl_clip.transition_out
        if t_out and t_out.effect == TransitionEffectEnum.FADE:
            clip = clip.with_effects([vfx.CrossFadeOut(EDLUtils.duration_to_seconds(duration=t_out.duration, fps=fps))])
        else:
            # Assume CUT. Only FADE & CUT supported for now
            pass
        
        return clip
        
    @staticmethod
    def black_frame(fps:int, resolution:tuple, start_time:float, num_frames:int=1)->tuple[ColorClip, float]:
        clip = ColorClip(size=resolution, color=(0,0,0)
                         ).with_start(start_time
                                      ).with_duration(round((num_frames / fps), 2))
                         
        end_time = start_time + clip.duration
        return clip, end_time