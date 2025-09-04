from moviepy import TextClip, ColorClip

from config.config import settings
from logger import logger
from movie_maker.movie_model import MovieModel
from movie_maker.edl_model import Clip, ClipTypeEnum, Duration
from movie_maker.effects import Effects
from movie_maker.edl_manager import EDLUtils
from ai.line_splitter import LineSplitter

class EndTitleManager():
    def __init__(self, end_titles:MovieModel.Configuration.EndTitles, resolution:tuple, fps:int, font_manager=None):
        self.end_titles = end_titles
        self.resolution = resolution
        self.fps = fps
        self.font_manager = font_manager
        
    def _line_splitter(self, text:str, mode:str)->tuple[str, int]:
        if (mode == 'AI'):
            line_splitter = LineSplitter()
            lines = line_splitter.intelligent_split(
                text=text,
                max_lines=settings.MovieMaker.EndTitles.General.MAX_LINES
            )
            num_lines = len(lines.splitlines())
        elif (mode == 'MoviePy'):
            lines = text
            # We don't know how many lines MoviePy 'automagically' splits the text into. Assume worst case
            num_lines = settings.MovieMaker.EndTitles.General.MAX_LINES
        else: # Manual
            lines = text
            num_lines = len(lines.splitlines())
            
        return (lines, num_lines)
    
    def remove_trailing_whitespaces(self, text: str) -> str:
        # Split the string into lines, remove trailing whitespaces, and join them back
        return "\n".join(line.rstrip() for line in text.splitlines())
            
    def generate_end_titles(self, clip_start_time:float, edl_clip:Clip)->tuple[list, float]:
        
        # Check if end_titles is None
        if not self.end_titles:
            logger.warning("EndTitleManager: end_titles is None, returning empty clips")
            return [], clip_start_time
        
        end_title_clips = []
        clip_duration = EDLUtils.duration_to_seconds(duration=edl_clip.duration, fps=self.fps)
        
        RESOLUTION = self.resolution
        
        # Step 1 - Add pre-transition frame
        # Append title clip to final video clip
        if edl_clip.transition_in and edl_clip.transition_in.transition_frame == True:
            black_frame, clip_start_time = Effects.black_frame(fps=self.fps, 
                                                                    resolution=RESOLUTION, 
                                                                    start_time=clip_start_time)
            end_title_clips.append(black_frame)
            
        # Step 2 - Add background clip 
        # Create a black background clip. This should come before text clips to ensure proper overlay
        background_clip = ColorClip(
            size=RESOLUTION,
            color=settings.MovieMaker.EndTitles.General.BG_COLOR
        ).with_start(clip_start_time).with_duration(clip_duration)
        # Add Transitions if necessary
        background_clip = Effects.apply_transition(clip=background_clip, edl_clip=edl_clip, fps=self.fps)
        
        
        # Step 3 - Add main title
        # Use main_title if available, otherwise use a generic fallback
        main_title_text = self.end_titles.main_title if self.end_titles.main_title else "PROPERTY ADDRESS"
        if not self.end_titles.main_title:
            logger.warning("EndTitleManager: main_title is None, using generic fallback")
            
        # Split the main text into lines
        main_text_lines, m_lines = self._line_splitter(
            text=main_title_text,
            mode=settings.MovieMaker.EndTitles.General.LINE_SPLIT_ALGO
        )
            
        m_start_x = settings.MovieMaker.EndTitles.Geometry.Landscape.H_MARGIN \
            if RESOLUTION[0] > RESOLUTION[1] \
                else settings.MovieMaker.EndTitles.Geometry.Portrait.H_MARGIN
        m_size_y = m_lines * settings.MovieMaker.EndTitles.Main.LINE_SIZE
        m_start_y = RESOLUTION[1]/2 - m_size_y - settings.MovieMaker.EndTitles.General.TITLES_GAP/2 \
            if (self.end_titles.sub_title and self.end_titles.sub_title.strip()) else \
                RESOLUTION[1]/2 - m_size_y/2
        m_size_x = RESOLUTION[0] - 2*settings.MovieMaker.EndTitles.Geometry.Landscape.H_MARGIN \
            if RESOLUTION[0] > RESOLUTION[1] \
                else RESOLUTION[0] - 2*settings.MovieMaker.EndTitles.Geometry.Portrait.H_MARGIN
        

        # Create TextClip for the main text
        # We don't know how many lines MoviePy 'automagically' splits the text into
        # As a result we need to create a tmp clip to fetch the actual number of text lines
        # and use that to create the final clip
        main_font = self.font_manager.get_font_path(ClipTypeEnum.TITLE) if self.font_manager else settings.MovieMaker.EndTitles.Main.Font.NAME
        main_text_clip_tmp = TextClip(
            text=main_text_lines,
            font_size=settings.MovieMaker.EndTitles.Main.Font.SIZE,
            size=(m_size_x,m_size_y),
            font=main_font,
            color=settings.MovieMaker.EndTitles.Main.Font.COLOR,
            margin=settings.MovieMaker.EndTitles.Main.FONT_MARGIN,
            method=settings.MovieMaker.EndTitles.General.METHOD,
            text_align=settings.MovieMaker.EndTitles.General.ALIGNMENT
        ).with_start(clip_start_time).with_duration(clip_duration
        ).with_position((m_start_x, m_start_y))
        
        main_text_lines, m_lines = self._line_splitter(
            text=main_text_clip_tmp.text,
            mode='Manual'
        )
        
        m_size_y = m_lines * settings.MovieMaker.EndTitles.Main.LINE_SIZE
        m_start_y = RESOLUTION[1]/2 - m_size_y - settings.MovieMaker.EndTitles.General.TITLES_GAP/2 \
            if (self.end_titles.sub_title and self.end_titles.sub_title.strip()) else \
                RESOLUTION[1]/2 - m_size_y/2
                
        # Create TextClip for the main text
        main_text_lines = self.remove_trailing_whitespaces(main_text_lines)
        main_text_clip = TextClip(
            text=main_text_lines,
            font_size=settings.MovieMaker.EndTitles.Main.Font.SIZE,
            size=(m_size_x,m_size_y),
            font=main_font,
            color=settings.MovieMaker.EndTitles.Main.Font.COLOR,
            margin=settings.MovieMaker.EndTitles.Main.FONT_MARGIN,
            method=settings.MovieMaker.EndTitles.General.METHOD,
            text_align=settings.MovieMaker.EndTitles.General.ALIGNMENT
        ).with_start(clip_start_time).with_duration(clip_duration
        ).with_position((m_start_x, m_start_y))
        
        # Add Transitions if necessary
        main_text_clip = Effects.apply_transition(clip=main_text_clip, edl_clip=edl_clip, fps=self.fps)
        
        # Step 4 - Add sub title
        sub_text_clip = None
        if self.end_titles.sub_title:
            # Split the subtext into lines
            sub_text_lines, s_lines = self._line_splitter(
                text=self.end_titles.sub_title,
                mode=settings.MovieMaker.EndTitles.General.LINE_SPLIT_ALGO
            )
            s_start_x = m_start_x
            s_size_y = s_lines * settings.MovieMaker.EndTitles.Sub.LINE_SIZE
            s_start_y = RESOLUTION[1]/2 + settings.MovieMaker.EndTitles.General.TITLES_GAP/2
            s_size_x = m_size_x
            
            # Create TextClip for the subtext
            # We don't know how many lines MoviePy 'automagically' splits the text into
            # As a result we need to create a tmp clip to fetch the actual number of text lines
            # and use that to create the final clip
            sub_font = self.font_manager.get_font_path(ClipTypeEnum.PROPERTY_LOCATION) if self.font_manager else settings.MovieMaker.EndTitles.Sub.Font.NAME
            sub_text_clip_tmp = TextClip(
                text=sub_text_lines,
                size=(s_size_x,s_size_y),
                font_size=settings.MovieMaker.EndTitles.Sub.Font.SIZE,
                font=sub_font,
                color=settings.MovieMaker.EndTitles.Sub.Font.COLOR,
                margin=settings.MovieMaker.EndTitles.Sub.FONT_MARGIN,
                method=settings.MovieMaker.EndTitles.General.METHOD,
                text_align=settings.MovieMaker.EndTitles.General.ALIGNMENT
            ).with_start(clip_start_time).with_duration(clip_duration
            ).with_position((s_start_x, s_start_y))
            
            sub_text_lines, s_lines = self._line_splitter(
                text=sub_text_clip_tmp.text,
                mode='Manual'
            )
            
            s_size_y = s_lines * settings.MovieMaker.EndTitles.Sub.LINE_SIZE
            s_start_y = RESOLUTION[1]/2 + settings.MovieMaker.EndTitles.General.TITLES_GAP/2
            
            # Create TextClip for the subtext
            sub_text_lines = self.remove_trailing_whitespaces(sub_text_lines)
            sub_text_clip = TextClip(
                text=sub_text_lines,
                size=(s_size_x,s_size_y),
                font_size=settings.MovieMaker.EndTitles.Sub.Font.SIZE,
                font=sub_font,
                color=settings.MovieMaker.EndTitles.Sub.Font.COLOR,
                margin=settings.MovieMaker.EndTitles.Sub.FONT_MARGIN,
                method=settings.MovieMaker.EndTitles.General.METHOD,
                text_align=settings.MovieMaker.EndTitles.General.ALIGNMENT
            ).with_start(clip_start_time).with_duration(clip_duration
            ).with_position((s_start_x, s_start_y))
            
            # Add Transitions if necessary
            sub_text_clip = Effects.apply_transition(clip=sub_text_clip, edl_clip=edl_clip, fps=self.fps)

        # Step 5 - Append background & text clips AFTER fully constructed - IN THIS ORDER
        end_title_clips.append(background_clip)
        end_title_clips.append(main_text_clip)
        if sub_text_clip:
            end_title_clips.append(sub_text_clip)
        
        # Step 6 - Update start time
        clip_start_time += clip_duration
            
        # Step 7 - Add post-transition frame
        if edl_clip.transition_out and edl_clip.transition_out.transition_frame == True:
            black_frame, clip_start_time = Effects.black_frame(fps=self.fps, 
                                                        resolution=RESOLUTION, 
                                                        start_time=clip_start_time)
            end_title_clips.append(black_frame)
        
        return end_title_clips, clip_start_time
    
    
def main():
    main_title = '7890 East Grandview Boulevard Mountain View Heights CA 94043'
    # main_title = '7890 East Grandview Boulevard Mountain View Heights CA'
    sub_title = '3 BED 2 BATH 1691 SF 5600 SF Lot $3288000'
    # sub_title = None

    RESOLUTION = settings.MovieMaker.Video.RESOLUTION_LANDSCAPE
    # RESOLUTION = settings.MovieMaker.Video.RESOLUTION_PORTRAIT
    FPS = settings.MovieMaker.Video.FRAME_RATE
    
    end_titles = MovieModel.Configuration.EndTitles(
        main_title=main_title,
        sub_title=sub_title
    )
    
    mgr = EndTitleManager(
        end_titles=end_titles,
        resolution=RESOLUTION,
        fps=FPS
    )
    
    title_clip_model = Clip(
        clip_number=1,
        clip_type=ClipTypeEnum.TITLE,
        duration=Duration(
            seconds=3,
            frames=0
        )
    )
    
    end_title_clips, _ = mgr.generate_end_titles(
        clip_start_time=0,
        edl_clip=title_clip_model
    )
              
    from moviepy import CompositeVideoClip
    video = CompositeVideoClip(clips=end_title_clips)
    # video.preview()
    
    orientation_suffix = 'landscape' \
        if RESOLUTION == settings.MovieMaker.Video.RESOLUTION_LANDSCAPE \
            else 'portrait'
    video_file_path = f'playground/samples/videos/end_titles_{orientation_suffix}_{settings.MovieMaker.EndTitles.General.LINE_SPLIT_ALGO}.mp4'
    logger.info(f'Writing final video to file')
    video.write_videofile(
        filename=video_file_path, 
        fps=FPS, 
        codec=settings.MovieMaker.Video.CODEC, 
        preset=settings.MovieMaker.Video.WRITE_SPEED,
        logger=None)
    
if __name__ == '__main__':
    main()
    
    
    
    
    
    
    
    