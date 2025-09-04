
from pathlib import Path
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper
import math
import abc

from gcp.secret import secret_mgr
import assemblyai as aai
from openai import OpenAI
import pysrt

from config.config import settings
from logger import logger

def _adjust_srt(srt_file_path:str):
    
    subs = pysrt.open(srt_file_path, encoding='utf-8')
    
    # Persist end for an additional amount of time
    last_sub = subs[-1]
    last_sub.end += int(settings.MovieMaker.Narration.Captions.END_PERSIST_DURATION * 1000) # ms
    
    subs.save(srt_file_path, encoding='utf-8')
    
class TrsanscriberBase(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def generate_captions_from_voiceover(self, voiceover_file_path:Path, srt_file:_TemporaryFileWrapper):
        return
    
class Transcriber():
    def __init__(self, max_char_per_segment:int):
        if settings.Engines.TRANSCRIBER == 'AssemblyAI':
            self.engine = Transcriber_AssemblyAI(
                max_char_per_segment=max_char_per_segment
            )
        elif settings.Engines.TRANSCRIBER == 'OpenAI':
            self.engine = Transcriber_OpenAI(
                max_char_per_segment=max_char_per_segment
            )
        
    def generate_captions_from_voiceover(self, 
                                         voiceover_file_path:Path, 
                                         srt_file:_TemporaryFileWrapper):
        
        return self.engine.generate_captions_from_voiceover(
            voiceover_file_path=voiceover_file_path,
            srt_file=srt_file
        )
        
class Transcriber_AssemblyAI(TrsanscriberBase):
    def __init__(self, max_char_per_segment:int):
        self.max_char_per_segment = max_char_per_segment
        aai.settings.api_key = secret_mgr.secret(settings.Secret.ASSEMBLY_AI_TRANSCRIBER_API_KEY)
        self.transcriber = aai.Transcriber()
    
    def generate_captions_from_voiceover(self, 
                                         voiceover_file_path:Path, 
                                         srt_file:_TemporaryFileWrapper):
        try:
            transcript = self.transcriber.transcribe(str(voiceover_file_path))
            srt_payload = transcript.export_subtitles_srt(chars_per_caption=self.max_char_per_segment)
            srt_file.write(srt_payload)
            srt_file.close()
            
            # Persist end for an additional amount of time
            _adjust_srt(srt_file_path=srt_file.name)
            
        except Exception as e:
            logger.exception(e)
            
class Transcriber_OpenAI(TrsanscriberBase):
    def __init__(self, max_char_per_segment:int):
        self.max_char_per_segment = max_char_per_segment
        self.client = OpenAI(api_key=secret_mgr.secret(settings.Secret.OPENAI_API_KEY))
        
    def generate_captions_from_script(self, script:str, duration:float, srt_file:_TemporaryFileWrapper):
        try:
            response = self.client.chat.completions.create(
                model=settings.OpenAI.Narration.CHAT_MODEL,
                messages=[
                    {
                    "role": "system",
                    "content": [
                        {
                        "type": "text",
                        "text": f"You are an expert at creating subtitles. \
                                You will be given a script \
                                You will need to create subtitles object (SRT format) based on the information given to you \
                                The duration of the SRT is {duration} seconds  \
                                You must also ensure that each line dones't exceed {self.max_char_per_segment} characters \
                                The segment timestamps should align with the number of words in a segment"
                        }]
                    },
                    {
                    "role": "user",
                    "content": [
                        {
                        "type": "text",
                        "text": f"{script}"
                        }
                        ]
                    },
                ],
                temperature=1,
                max_tokens=settings.OpenAI.Narration.RESPONSE_TOKEN_LIMIT,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                response_format={
                    "type": "text"
                }
            )

            srt_payload = response.choices[0].message.content
            srt_file.write(srt_payload)
            srt_file.close()
            
            # Persist end for an additional amount of time
            _adjust_srt(srt_file_path=srt_file.name)
            
        except Exception as e:
            logger.exception(e)
    
    def generate_captions_from_voiceover(self, voiceover_file_path:Path, srt_file:_TemporaryFileWrapper):
        def format_time(seconds):
            hours = math.floor(seconds / 3600)
            seconds %= 3600
            minutes = math.floor(seconds / 60)
            seconds %= 60
            milliseconds = round((seconds - math.floor(seconds)) * 1000)
            seconds = math.floor(seconds)
            formatted_time = f"{hours:02d}:{minutes:02d}:{seconds:01d},{milliseconds:03d}"
            return formatted_time

        def transcribe_audio(audio_file_path):
            #model = WhisperModel("small") Need to import Whisper before using this model
            model = None
            segments, info = model.transcribe(audio_file_path)
            language = info[0]
            
            segments = list(segments)  # The transcription will actually run here.
            return language, segments
        
        def split_text_intelligently(text, max_words_per_line):
            """
            Splits text into chunks of up to max_words_per_line words,
            breaking at punctuation marks when possible.
            """
            import re

            words = text.split()
            lines = []
            start = 0
            while start < len(words):
                end = min(start + max_words_per_line, len(words))

                # Try to find a punctuation mark within the current chunk
                split_found = False
                for i in range(end, start, -1):
                    if re.match(r'.*[\.,;!?]$', words[i-1]):
                        lines.append(' '.join(words[start:i]))
                        start = i
                        split_found = True
                        break
                if not split_found:
                    lines.append(' '.join(words[start:end]))
                    start = end
            return lines
        
        try:
            _, segments = transcribe_audio(audio_file_path=voiceover_file_path)
            max_words_per_line = settings.MovieMaker.Narration.Captions.TRANSCRIBER_MAX_WORDS_PER_LINE

            srt_content = ""
            segment_counter = 0

            for segment in segments:
                segment_text = segment.text.strip()
                words_in_segment = segment_text.split()
                num_words_in_segment = len(words_in_segment)

                if num_words_in_segment <= max_words_per_line:
                    # Keep the segment as is
                    segment_counter += 1
                    segment_start = format_time(segment.start)
                    segment_end = format_time(segment.end)
                    srt_content += f"{segment_counter}\n"
                    srt_content += f"{segment_start} --> {segment_end}\n"
                    srt_content += f"{segment_text}\n\n"
                else:
                    # Split the segment.text into lines of up to max_words_per_line
                    lines = split_text_intelligently(segment_text, max_words_per_line)
                    # Calculate duration per word in the original segment
                    duration = segment.end - segment.start
                    duration_per_word = duration / num_words_in_segment
                    # Create new segments for each line
                    current_time = segment.start
                    for line in lines:
                        words_in_line = len(line.split())
                        line_duration = words_in_line * duration_per_word
                        end_time = current_time + line_duration
                        # Ensure that end_time does not exceed the segment's end time
                        if end_time > segment.end:
                            end_time = segment.end
                        segment_counter += 1
                        formatted_start = format_time(current_time)
                        formatted_end = format_time(end_time)
                        srt_content += f"{segment_counter}\n"
                        srt_content += f"{formatted_start} --> {formatted_end}\n"
                        srt_content += f"{line}\n\n"
                        current_time = end_time  # Update for next line
            
            srt_file.write(srt_content)
            srt_file.close()
            
        except Exception as e:
            logger.exception(e)
        
def main():
    
    transcriber = Transcriber()
    voiceover_file_path = Path('Editor/Playground/Captions/audio.mp3')
    with NamedTemporaryFile(mode='w+t', suffix='.srt', delete_on_close=False) as srt_file:
        _ = transcriber.generate_captions_from_voiceover(
            voiceover_file_path=voiceover_file_path,
            srt_file=srt_file)
        
if __name__ == "__main__":
    main()