from pathlib import Path

from moviepy import AudioFileClip, CompositeAudioClip, afx

from config.config import settings
from logger import logger
from utils.audio_utils import *


class AudioHandler:
    def __init__(
        self,
        video_duration: float,
        bg_music_file_path: Path = None,
        voiceover_file_path: Path = None,
    ):
        self.video_duration = video_duration
        self.bg_music_file_path = bg_music_file_path
        self.voiceover_file_path = voiceover_file_path

    def gen_audio_tracks(self) -> CompositeAudioClip:
        """
        Adds background music and voiceover to the video.

        Args:
            video: MoviePy VideoClip object.
            bg_music_file_path (Path, optional): Path to the music audio file.
            voiceover_file_path (Path, optional): Path to the voiceover audio file.

        Returns:
            CompositeAudioClip: Combined audio clip.
        """

        video_duration = self.video_duration
        bg_music_file_path = self.bg_music_file_path
        voiceover_file_path = self.voiceover_file_path

        if not bg_music_file_path and not voiceover_file_path:
            logger.warning(
                f"No soundtrack to add as neither music or voiceover tracks were provided."
            )
            return None

        mixed_audio = None

        if bg_music_file_path:
            logger.debug(f"Add music to video")
        if voiceover_file_path:
            logger.debug(f"Adding voiceover to video")

        # Add background music
        if bg_music_file_path and bg_music_file_path.exists():
            try:
                # Adjust volume as needed
                bg_music = AudioFileClip(str(bg_music_file_path)).with_volume_scaled(
                    settings.MovieMaker.Music.VOLUME_RATIO_WITH_VOICEOVER
                    if voiceover_file_path
                    else settings.MovieMaker.Music.VOLUME_RATIO_WITHOUT_VOICEOVER
                )
                if bg_music.duration > video_duration:
                    bg_music = bg_music.subclipped(0, video_duration).with_effects(
                        [afx.AudioFadeOut(settings.Music.FADEOUT_DURATION)]
                    )

                if settings.Music.PLAY_IN_LOOP == True:
                    bg_music = afx.audio_loop(bg_music, duration=video_duration)

                mixed_audio = CompositeAudioClip(
                    [bg_music.with_start(settings.MovieMaker.Music.OFFSET)]
                )

                logger.info(f"Added background music")
            except Exception as e:
                logger.error(
                    f"Error loading background music file {bg_music_file_path}: {e}"
                )
                raise e

        # Add voiceover
        if voiceover_file_path and voiceover_file_path.exists():
            try:
                voiceover = AudioFileClip(str(voiceover_file_path)).with_volume_scaled(
                    settings.MovieMaker.Narration.Voiceover.VOLUME_RATIO
                )  # Adjust volume as needed
                # Optionally, set the start time of the voiceover
                voiceover = voiceover.with_duration(
                    min(voiceover.duration, video_duration)
                )
                if mixed_audio:
                    mixed_audio = CompositeAudioClip(
                        [
                            mixed_audio,
                            voiceover.with_start(
                                settings.MovieMaker.Narration.Voiceover.START_OFFSET
                            ),
                        ]
                    )
                else:
                    mixed_audio = CompositeAudioClip(
                        [
                            voiceover.with_start(
                                settings.MovieMaker.Narration.Voiceover.START_OFFSET
                            )
                        ]
                    )
                logger.info(f"Added voiceover")
            except Exception as e:
                logger.error(f"Error loading voiceover {voiceover_file_path}: {e}")

        return mixed_audio
