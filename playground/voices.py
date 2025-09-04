import os
import argparse
from pathlib import Path
from rich import print
from pydantic import AnyUrl

from gcp.db import db_client
from gcp.storage import StorageManager, CloudPath
from config.config import settings
from logger import logger
from movie_maker.voiceover_model import ElevenLabs
from movie_maker.voiceover_manager import VoiceoverManager
from movie_maker.movie_model import MovieModel
from ai.tts import TTS

SAMPLES_ID = 'Samples'
SCRIPT_ID = 'voiceover_script'
VOICEOVER_SAMPLES_DIR = 'library/voiceover_samples'

class Voices_ElevenLabs():

    def __init__(self):
        self.voiceover_manager = VoiceoverManager()
    
    def download_mapping(self)->ElevenLabs:
        """Download the latest active voice mappings from Firestore"""
        voice_mappings = self.voiceover_manager.get_voice_mappings()
        if not voice_mappings:
            raise FileNotFoundError(f"Voice mappings document doesn't exist in Firestore")
        return voice_mappings
        
    def upload_mapping(self, model:ElevenLabs):
        """Upload voice mappings to Firestore with versioning support"""
        self.voiceover_manager.save_voice_mappings(model)
        
    def fetch_script(self)->str:
        samples_ref = db_client.collection(
            settings.GCP.Firestore.VOICEOVER_COLLECTION_NAME).document(
                document_id=SAMPLES_ID)
            
        samples_doc = samples_ref.get()
        if not samples_doc.exists:
            raise FileNotFoundError(
                f'`{SAMPLES_ID}` doc not found in Firestore collection \
                    `{settings.GCP.Firestore.VOICEOVER_COLLECTION_NAME}`')
            
        script = samples_doc.to_dict()[SCRIPT_ID]
        return script

    def gen_audio_samples(self, model:ElevenLabs, script:str):
        tts_mgr = TTS()
        
        # Create version-specific subdirectory
        version_dir = f'{VOICEOVER_SAMPLES_DIR}/v{model.version_info.version}'
        os.makedirs(version_dir, exist_ok=True)
        
        for voice in model.voice_mappings:
            tts_mgr.generate_voiceover(
                file_path=f'{version_dir}/{voice.id}.wav',
                narration=MovieModel.Configuration.Narration(
                    enabled=True,
                    voice=voice.id, 
                    script=script
                )
            )
            
    def link_audio_samples(self, model:ElevenLabs)->ElevenLabs:
        return self.voiceover_manager.link_audio_samples(model)
            
    def upload_audio_samples(self):
        storage_mgr = StorageManager()
        bucket_id = settings.GCP.Storage.TEMPLATES_BUCKET
        cloud_folder = settings.MovieMaker.Narration.Voiceover.MAPPINGS_STORAGE_DIR_PREFIX
        
        # Get latest version from voiceover manager
        latest_model = self.voiceover_manager.get_voice_mappings()
        
        # Determine source directory
        if latest_model and latest_model.version_info:
            # Use version-specific directory if version exists
            source_dir = Path(f'{VOICEOVER_SAMPLES_DIR}/v{latest_model.version_info.version}')
        else:
            # Fall back to base directory if no version
            source_dir = Path(VOICEOVER_SAMPLES_DIR)
            
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory {source_dir} not found")
            
        storage_mgr.save_blobs(source_dir=source_dir,
                             cloud_path=CloudPath(
                                 bucket_id=bucket_id,
                                 path=Path(cloud_folder)
                             ))
        
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Editora video maker')
    parser.add_argument('-v', '--validate', action='store_true', help='Download & validate mappings')
    parser.add_argument('-l', '--link_audio_samples', action='store_true', help='Link audio samples to mappings')
    parser.add_argument('-s', '--save', action='store_true', help='Save / Upload mappings')
    parser.add_argument('--save_audio_samples', action='store_true', help='Save audio samples in cloud storage')
    parser.add_argument('--gen_audio_samples', action='store_true', help='Generate audio samples for all voices')
    parser.add_argument('-r', '--regenerate', action='store_true', help='The whole 9 yards!')
    args = parser.parse_args()
    
    voices_mgr = Voices_ElevenLabs()
    
    model = ElevenLabs(
        voice_mappings=[
            ElevenLabs.Mapping(id='JBFqnCBsd6RMkjVDRZzb', eleven_labs_name='George', editora_name='EDWARD', description='Dramatic brit', sample_audio_uri=AnyUrl('gs://editora-v2-templates/voiceover/JBFqnCBsd6RMkjVDRZzb.wav'), rank=5),
            ElevenLabs.Mapping(id='dJyq5Xykp4DLgX0pLAj8', eleven_labs_name='Timmy', editora_name='KEVIN', description='Middle aged american', sample_audio_uri=AnyUrl('gs://editora-v2-templates/voiceover/8MgTA8Im7tLV875Wx2zV.wav'), rank=6),
            ElevenLabs.Mapping(id='2qfp6zPuviqeCOZIE9RZ', eleven_labs_name='Christina', editora_name='AMARA', description='Calming yoga instructor', sample_audio_uri=AnyUrl('gs://editora-v2-templates/voiceover/2qfp6zPuviqeCOZIE9RZ.wav'), rank=8),
            ElevenLabs.Mapping(id='z7U1SjrEq4fDDDriOQEN', eleven_labs_name='Vivie', editora_name='ISABELLE', description='Cultured, intelligent', sample_audio_uri=AnyUrl('gs://editora-v2-templates/voiceover/z7U1SjrEq4fDDDriOQEN.wav'), rank=4),
            ElevenLabs.Mapping(id='qK0OgGvRPnN4xJTPADgL', eleven_labs_name='Theresa', editora_name='VICTORIA', description='Formal and smart', sample_audio_uri=AnyUrl('gs://editora-v2-templates/voiceover/C0pNWoAGHvjWWAv6hrRW.wav'), rank=1),
            ElevenLabs.Mapping(id='WnITnO5103WxRvv07sz5', eleven_labs_name='Susannah', editora_name='SARAH', description='NA', sample_audio_uri=AnyUrl('gs://editora-v2-templates/voiceover/Q5ZUPBEzI453ysQJBP96.wav'), rank=3),
            ElevenLabs.Mapping(id='aMSt68OGf4xUZAnLpTU8', eleven_labs_name='Juniper', editora_name='LARA', description='NA', sample_audio_uri=AnyUrl('gs://editora-v2-templates/voiceover/aMSt68OGf4xUZAnLpTU8.wav'), rank=7)
        ],
        version_info=ElevenLabs.VersionInfo(version=1)
    )
    
    if args.validate:
        model = voices_mgr.download_mapping()
        print(model.model_dump_json(indent=2))
        
    if args.link_audio_samples:
        model = voices_mgr.download_mapping()
        model = voices_mgr.link_audio_samples(model=model)
        voices_mgr.upload_mapping(model=model)
        
    if args.save:
        if model:
            voices_mgr.upload_mapping(model=model)
        else:
            logger.error("No mapping to upload")
            
    if args.save_audio_samples:
        voices_mgr.upload_audio_samples()

    if args.gen_audio_samples:
        script = voices_mgr.fetch_script()
        logger.info(f'SCRIPT : {script}')
        voices_mgr.gen_audio_samples(model=model, script=script)
        logger.info('Generated audio samples for all voices')
        
    if args.regenerate:
        script = voices_mgr.fetch_script()
        logger.info(f'SCRIPT : {script}')
        
        # model = voices_mgr.download_mapping()
        # logger.info('Downloaded mappings')
        
        model = model
        logger.info('Fetched local mappings')
        
        voices_mgr.gen_audio_samples(model=model, script=script)
        logger.info('Generated audio samples for all voices')
        
        voices_mgr.upload_audio_samples()
        logger.info(f'Stored audio samples in cloud for all voices')
        
        voices_mgr.link_audio_samples(model=model)
        logger.info(f'Linked audio samples to mapping')
        
        voices_mgr.upload_mapping(model=model)
        logger.info(f'Upload mapping')