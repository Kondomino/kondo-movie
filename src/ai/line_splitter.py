from openai import OpenAI
from gcp.secret import secret_mgr

from config.config import settings

class LineSplitter():
    def __init__(self):
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
            return f"An error occurred: {e}"