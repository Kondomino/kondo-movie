from openai import OpenAI
from gcp.secret import secret_mgr
from logger import logger

from config.config import settings

class LineSplitter():
    def __init__(self):
        if not settings.FeatureFlags.ENABLE_OPENAI:
            logger.warning("LineSplitter initialized but OpenAI is disabled")
            self.client = None
            return
        self.client = OpenAI(api_key=secret_mgr.secret(settings.Secret.OPENAI_API_KEY))
        
    def intelligent_split(
        self,
        text:str, 
        max_lines:int):
        
        """
        Splits the input text into multiple lines intelligently based on readability and context,
        using AI to ensure as few lines as possible up to max_lines.

        Args:
            text (str): The string to be split.
            max_lines (int): Maximum number of lines allowed.

        Returns:
            str: A multi-line string with at most max_lines lines.
        """
        
        if not settings.FeatureFlags.ENABLE_OPENAI or self.client is None:
            logger.warning("OpenAI line splitting called but service is disabled - using basic splitting")
            # Fallback to basic line splitting
            words = text.split()
            lines = []
            current_line = []
            words_per_line = len(words) // max_lines + 1
            
            for i, word in enumerate(words):
                current_line.append(word)
                if len(current_line) >= words_per_line or i == len(words) - 1:
                    lines.append(' '.join(current_line))
                    current_line = []
                    if len(lines) >= max_lines:
                        break
            
            return '\n'.join(lines)

        try:
            response = self.client.chat.completions.create(
                model=settings.OpenAI.Narration.CHAT_MODEL,
                messages=[
                    {
                        "role": "system", 
                        "content": [{
                            "type": "text",
                            "text": f" You are an assistant that formats text for readability. \
                                    Given the following input text, split it into as few lines as possible \
                                    (up to a maximum of {max_lines} lines) \
                                    without breaking important information or entities. \
                                    Ensure that each line maintains context and readability."    
                        }]
                    },
                    {
                        "role": "user",
                        "content": [{
                            "type": "text",
                            "text": f"{text}"
                        }]
                    },
                ],
                temperature=0.1,
                max_tokens=1024,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                response_format={
                    "type": "text"
                }
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"OpenAI line splitting failed: {str(e)} - using basic splitting")
            # Fallback to basic line splitting
            words = text.split()
            lines = []
            current_line = []
            words_per_line = len(words) // max_lines + 1
            
            for i, word in enumerate(words):
                current_line.append(word)
                if len(current_line) >= words_per_line or i == len(words) - 1:
                    lines.append(' '.join(current_line))
                    current_line = []
                    if len(lines) >= max_lines:
                        break
            
            return '\n'.join(lines)