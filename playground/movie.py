from tempfile import NamedTemporaryFile
from pathlib import Path
import os
import math
import pillow_avif

from moviepy import CompositeVideoClip, vfx

from logger import logger
from config.config import settings
from movie_maker.movie_model import MovieModel
from movie_maker.edl_model import *
from movie_maker.watermark import Watermark
from movie_maker.end_titles import EndTitleManager
from movie_maker.captions import CaptionsManager
from movie_maker.effects import Effects

from ai.tts import TTS

def main():
    RESOLUTION = settings.MovieMaker.Video.RESOLUTION_LANDSCAPE
    # RESOLUTION = settings.MovieMaker.Video.RESOLUTION_PORTRAIT
    FPS = 30
    DURATION = 3
    TRANSITION_DURATION = 0.5
    NUM_CLIPS = 4
    narration = MovieModel.Configuration.Narration(
        enabled=True,
        voice=settings.OpenAI.Narration.TTS.VOICE,
        script="""
            This charming 3-bedroom, 2-bathroom Queen Anne cottage is nestled in the 
            highly sought-after and historic Professorville neighborhood of Palo Alto. 
            With its timeless architectural details and prime location, 
            this property offers incredible potential for transformation or expansion. 
        """,
        captions=True
    )
    edl_clip = Clip(
        clip_number=1,
        clip_type=ClipTypeEnum.TITLE,
        duration=Duration(seconds=2, frames=0),
        clip_effect=ClipEffectEnum.ZOOM_IN,
        transition_in=Transition(
            effect=TransitionEffectEnum.FADE,
            duration=Duration(seconds=0, frames=15)
        ),
        transition_out=Transition(
            effect=TransitionEffectEnum.FADE,
            duration=Duration(seconds=0, frames=15),
            transition_frame=True
        )
    )
    add_watermark = True
    add_endtitles = False
    
    image_folder = '/Users/kishanj/Coding/Projects/Editora/Code/editora-v2-movie-maker/playground/samples/images/set1'
    clips = []  
    clip_start_time = 0
    for clip_count, filename in enumerate(os.listdir(image_folder), start=0):
        if clip_count >= NUM_CLIPS:
            break
        image_path = os.path.join(image_folder, filename)
        if os.path.isfile(image_path):
            clip = Effects.gen_imageclip(image_path=image_path, resolution=RESOLUTION)
            # x_extend = math.ceil(DURATION*FPS*settings.MovieMaker.Image.PAN_SPEED)
            # clip = Effects.gen_imageclip(image_path=image_path, resolution=(RESOLUTION[0]+x_extend, RESOLUTION[1]))
            
            clip = clip.with_start(clip_start_time).with_duration(DURATION)
            # clip = Effects.pan_right(clip=clip, fps=FPS, resolution=RESOLUTION)
            
            if TRANSITION_DURATION:
                clip = clip.with_effects([vfx.CrossFadeIn(TRANSITION_DURATION), vfx.CrossFadeOut(TRANSITION_DURATION)])
            clips.append(clip)
            clip_start_time += clip.duration
    
    if add_endtitles:
        endtitles_model = MovieModel.Configuration.EndTitles(
            main_title='Hello, how are you doing?',
            sub_title='World!'
        )
        endtitles_mgr = EndTitleManager(end_titles=endtitles_model, resolution=RESOLUTION, fps=FPS)
        endtitle_clips, clip_start_time = endtitles_mgr.generate_end_titles(
            clip_start_time=clip_start_time, 
            edl_clip=edl_clip)
        clips.extend(endtitle_clips)
        # clips.append(black_frame)
    
    voiceover_file_path = None
    
    
    if narration.enabled == True:
        with NamedTemporaryFile(suffix='.wav') as voiceover_file:
            voiceover_file_path = voiceover_file.name
            tts = TTS()
            tts.generate_voiceover(
                file_path=Path(voiceover_file_path), 
                narration=narration)
            
            if narration.captions:
                captions_mgr = CaptionsManager(
                    resolution=RESOLUTION,
                )
                subtitles, srt_file_path = captions_mgr.generate_captions(
                    voiceover_file_path=voiceover_file_path
                )
                clips.append(subtitles)
                os.remove(srt_file_path)    
    
    if add_watermark:    
        watermark = Watermark(resolution=RESOLUTION, duration=clip_start_time).generate_watermark_clip()
        clips.append(watermark)
    
    video = CompositeVideoClip(clips=clips)
    
    video_file = 'playground/samples/videos/video_portrait.mp4' \
        if RESOLUTION == settings.MovieMaker.Video.RESOLUTION_PORTRAIT \
            else 'playground/samples/videos/video_landscape.mp4'
    video.write_videofile(
        filename=video_file, 
        fps=FPS, 
        codec=settings.MovieMaker.Video.CODEC, 
        threads=settings.MovieMaker.Video.THREADS,
        preset=settings.MovieMaker.Video.WRITE_SPEED,
        logger=None)
    
if __name__ == '__main__':
    main()
    
    
    