from pathlib import Path
from typing import Iterator, Literal
import abc

from openai import OpenAI
from elevenlabs import ElevenLabs, VoiceSettings
from gcp.secret import secret_mgr

from config.config import settings
from utils.audio_utils import *
from movie_maker.movie_model import MovieModel

class TTS():
    def __init__(self):
        # Check feature flags before initializing engines
        if settings.Engines.TTS == 'ElevenLabs':
            if settings.FeatureFlags.ENABLE_ELEVEN_LABS:
                self.engine = TTS_ElevenLabs()
            else:
                logger.warning("ElevenLabs TTS disabled via feature flag - using mock TTS engine")
                self.engine = TTS_Mock()
        elif settings.Engines.TTS == 'OpenAI':
            if settings.FeatureFlags.ENABLE_OPENAI:
                self.engine = TTS_OpenAI()
            else:
                logger.warning("OpenAI TTS disabled via feature flag - using mock TTS engine")
                self.engine = TTS_Mock()
        else:
            logger.warning(f"Unknown TTS engine '{settings.Engines.TTS}' - using mock TTS engine")
            self.engine = TTS_Mock()
        
    def generate_voiceover(self, file_path:Path, 
                           narration:MovieModel.Configuration.Narration,
                           output_format:Literal['mp3', 'wav']='wav',
                           desired_duration_window:tuple[float, float]=None,
                           allowable_adjustment_factor:tuple[float, float]=\
                            settings.MovieMaker.Narration.Voiceover.MAX_ADJUSTMENT_FACTOR):
        
        def _audio_to_file(audio, file_path):
            with open(file_path, "wb") as f:
                for chunk in audio:
                    if chunk:
                        f.write(chunk)
                        
        # Step 1 : Generate VO from script
        audio_in = self.engine.generate_voiceover(
            script=narration.script,
            voice=narration.voice,
            output_format=output_format
        )
        
        # Step 2 : Make adjustments to VO duration if necessary 
        audio_out = adjust_audio(
            audio_in=audio_in,
            format=output_format,
            desired_duration_window=desired_duration_window,
            allowable_adjustment_factor=allowable_adjustment_factor
        )
        
        # Step 3: Write to file
        _audio_to_file(audio_out, file_path)
        
        # Step 4: Normalize audio in place
        normalize_audio(file_path, file_path)
        
class TTSBase(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def generate_voiceover(self, script:str, voice:str=None, output_format:Literal['mp3', 'wav']=None)->Iterator[bytes]:
        return
    
class TTS_OpenAI(TTSBase):
    def __init__(self):
        if not settings.FeatureFlags.ENABLE_OPENAI:
            logger.warning("TTS_OpenAI initialized but OpenAI is disabled")
            self.client = None
            return
        self.client = OpenAI(api_key=secret_mgr.secret(settings.Secret.OPENAI_API_KEY))
        
    def generate_voiceover(self, script:str, voice:str=None, output_format:Literal['mp3', 'wav']='wav')->Iterator[bytes]:
        if not settings.FeatureFlags.ENABLE_OPENAI or self.client is None:
            logger.error("OpenAI TTS called but service is disabled")
            return iter([])
            
        response = self.client.audio.speech.create(
            model=settings.OpenAI.Narration.TTS.MODEL,
            voice=voice if voice else settings.OpenAI.Narration.TTS.VOICE,
            input=script,
            response_format=output_format
        )
        return response.iter_bytes()
        
class TTS_ElevenLabs(TTSBase):
    FORMAT_MAP = {
        'mp3': 'mp3_44100_128',
        'wav': 'pcm_24000'
    }
    
    def __init__(self):
        if not settings.FeatureFlags.ENABLE_ELEVEN_LABS:
            logger.warning("TTS_ElevenLabs initialized but ElevenLabs is disabled")
            self.client = None
            return
        self.client = ElevenLabs(
            api_key=secret_mgr.secret(settings.Secret.ELEVEN_LABS_API_KEY)
        )
        
    def generate_voiceover(self, script:str, voice:str=None, output_format:Literal['mp3', 'wav']='wav')->Iterator[bytes]:
        if not settings.FeatureFlags.ENABLE_ELEVEN_LABS or self.client is None:
            logger.error("ElevenLabs TTS called but service is disabled")
            return iter([])
            
        kwargs = {
            'model': settings.ElevenLabs.TTS.MODEL,
            'voice': voice if voice else settings.ElevenLabs.TTS.VOICE,
            'voice_settings': VoiceSettings(
                stability=settings.ElevenLabs.TTS.VoiceSettings.STABILITY, 
                similarity_boost=settings.ElevenLabs.TTS.VoiceSettings.SIMILARITY_BOOST, 
                style=settings.ElevenLabs.TTS.VoiceSettings.STYLE, 
                use_speaker_boost=settings.ElevenLabs.TTS.VoiceSettings.USE_SPEAKER_BOOST
            ),
            'text': script,
            'output_format': TTS_ElevenLabs.FORMAT_MAP[output_format]
        }
            
        return self.client.generate(**kwargs)

class TTS_Mock(TTSBase):
    """Mock TTS engine for when TTS services are disabled"""
    
    def generate_voiceover(self, script:str, voice:str=None, output_format:Literal['mp3', 'wav']='wav')->Iterator[bytes]:
        logger.info(f"[TTS_MOCK] TTS request for script: '{script}' with voice: '{voice}' (service disabled)")
        # Return empty audio data - this will result in silent videos
        return iter([])

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate voiceover using ElevenLabs TTS')
    parser.add_argument('--input_file', type=str, help='Input text file containing the script')
    parser.add_argument('--output_file', type=str, help='Output audio file path (supported: .mp3, .wav)')
    parser.add_argument('--voice', type=str, help='Voice ID to use for TTS', default=None)
    args = parser.parse_args()
    
    # Read input script
    with open(args.input_file, 'r') as f:
        script = f.read().strip()
    
    # Determine output format from file extension
    output_path = Path(args.output_file)
    output_format = output_path.suffix.lstrip('.')
    
    if output_format not in ('mp3', 'wav'):
        raise ValueError(f"Unsupported output format: {output_format}. Supported formats: mp3, wav")
    
    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Generate voiceover
    tts = TTS()
    narration = MovieModel.Configuration.Narration(script=script, voice=args.voice)
    
    tts.generate_voiceover(
        file_path=output_path,
        narration=narration,
        output_format=output_format,
    )
    
    print("Done!")

if __name__ == '__main__':
    main()