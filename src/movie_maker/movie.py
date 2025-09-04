from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from moviepy import CompositeVideoClip

from logger import logger
from config.config import settings
from movie_maker.video_generation import VideoGenerator
from movie_maker.audio_handler import AudioHandler
from movie_maker.movie_model import MovieModel, MovieMakerResponseModel
from movie_maker.edl_model import EDL, ClipTypeEnum
from movie_maker.captions import CaptionsManager
from movie_maker.watermark import Watermark
from ai.tts import TTS
from gcp.storage import StorageManager, CloudPath


class MovieMaker:
    def __init__(self, movie_model: MovieModel):
        self.movie_model = movie_model
        if (
            movie_model.config.image_orientation
            == MovieModel.Configuration.Orientation.Portrait
        ):
            self.RESOLUTION = settings.MovieMaker.Video.RESOLUTION_PORTRAIT
        else:
            self.RESOLUTION = settings.MovieMaker.Video.RESOLUTION_LANDSCAPE

    @staticmethod
    def image_clip_count(edl: EDL, config: MovieModel.Configuration):
        total_clips = len(edl.clips)
        num_title_and_presents_clips = sum(
            clip.clip_type
            in [
                ClipTypeEnum.TITLE,
                ClipTypeEnum.PRESENTS,
                ClipTypeEnum.AGENT_LOGO,
                ClipTypeEnum.BROKERAGE_LOGO,
                ClipTypeEnum.AGENT_NAME,
            ]
            for clip in edl.clips
        )

        return (
            total_clips
            if not config.end_titles
            else (total_clips - num_title_and_presents_clips)
        )

    def make_movie(self) -> MovieMakerResponseModel:
        try:
            music_file_path = None

            movie_model = self.movie_model
            edl = movie_model.edl

            # Generate video
            video_generator = VideoGenerator(
                edl=edl,
                ordered_images=self.movie_model.ordered_images,
                movie_model=movie_model,
                resolution=self.RESOLUTION,
            )

            clips, video_duration, used_images = video_generator.generate_video()
            logger.info(f"Composed base video. Duration : {video_duration:.2f} seconds")

            if movie_model.config.music:
                if edl.soundtrack_uri:
                    # Get extension from soundtrack URI
                    soundtrack_ext = Path(str(edl.soundtrack_uri)).suffix
                    with NamedTemporaryFile(
                        delete=False, suffix=soundtrack_ext
                    ) as music_file:
                        music_file_path = music_file.name
                        StorageManager.load_blob(
                            cloud_path=CloudPath.from_path(str(edl.soundtrack_uri)),
                            dest_file=Path(music_file_path),
                        )
                else:
                    logger.warning(
                        f"EDL '{edl.name}' doesn't have a soundtrack associated with it"
                    )

            voiceover_file_path = None
            srt_file_path = None
            subtitles = None
            tts = TTS()
            narration = self.movie_model.config.narration

            if narration.enabled and narration.script:
                with NamedTemporaryFile(delete=False, suffix=".wav") as voiceover_file:
                    voiceover_file_path = voiceover_file.name
                    max_voiceover_duration = (
                        video_duration
                        - settings.MovieMaker.Narration.Voiceover.START_OFFSET
                        - settings.MovieMaker.Narration.Voiceover.END_OFFSET
                    )
                    min_voiceover_duration = (
                        max_voiceover_duration
                        - settings.MovieMaker.Narration.Voiceover.DURATION_VARIANCE
                    )
                    tts.generate_voiceover(
                        file_path=Path(voiceover_file_path),
                        narration=narration,
                        output_format="wav",
                        desired_duration_window=(
                            min_voiceover_duration,
                            max_voiceover_duration,
                        ),
                    )

                    if narration.captions:
                        captions_mgr = CaptionsManager(
                            resolution=self.RESOLUTION,
                        )
                        subtitles, srt_file_path = captions_mgr.generate_captions(
                            voiceover_file_path=voiceover_file_path
                        )
                        clips.append(subtitles)

            if self.movie_model.config.watermark:
                watermark = Watermark(
                    self.RESOLUTION, duration=video_duration
                ).generate_watermark_clip()
                clips.append(watermark)

            video = CompositeVideoClip(clips=clips)

            audio_handler = AudioHandler(
                video_duration=video.duration,
                bg_music_file_path=Path(music_file_path) if music_file_path else None,
                voiceover_file_path=(
                    Path(voiceover_file_path) if voiceover_file_path else None
                ),
            )
            audio = audio_handler.gen_audio_tracks()

            if audio:
                final_video = video.with_audio(audio)
            else:
                final_video = video

            with NamedTemporaryFile(delete=False, suffix=".mp4") as video_file:
                logger.info(f"Writing final video to file")
                final_video.write_videofile(
                    filename=video_file.name,
                    fps=edl.fps,
                    codec=settings.MovieMaker.Video.CODEC,
                    audio_codec=settings.MovieMaker.Video.AUDIO_CODEC,
                    threads=settings.MovieMaker.Video.THREADS,
                    preset=settings.MovieMaker.Video.WRITE_SPEED,
                    logger=None,
                )
                final_video.close()

            return MovieMakerResponseModel(
                video_file_path=Path(video_file.name),
                voiceover_file_path=voiceover_file_path,
                captions_file_path=srt_file_path,
                used_images=used_images,
            )

        except Exception as e:
            logger.exception(f"Failed to export video: {e}")
            raise e

        finally:
            if music_file_path and os.path.exists(music_file_path):
                os.remove(str(music_file_path))
