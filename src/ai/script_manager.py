
import argparse
from rich import print

from openai import OpenAI

from config.config import settings
from logger import logger
from gcp.secret import secret_mgr

        
class ScriptManager():
    
    def __init__(self):
        self.client = OpenAI(api_key=secret_mgr.secret(settings.Secret.OPENAI_API_KEY))

    def generate_script(self, description:str):
        num_attempts = 0
        while True:
            response = self.client.chat.completions.create(
                model=settings.OpenAI.Narration.CHAT_MODEL,
                messages=[
                    {
                    "role": "system",
                    "content": [
                        {
                        "type": "text",
                        "text": f"""
                            You are a professional real estate voiceover scriptwriter.
                            Your task is to generate a concise, polished voiceover script based on the provided property description. The tone should reflect the original listing writer’s voice — since the listing is often written by the agent, the script should feel familiar and natural to them. Avoid adding generic or overly salesy language that wasn’t in the original (e.g., “perfect for you”).

                            **Rules:**
                            - The script must be **{settings.OpenAI.Narration.SCRIPT_CHAR_LIMIT} characters or fewer**. Validate the character count before returning the final output.
                            - **Use the tone and language style of the original listing**, unless it's awkward or grammatically incorrect, then improve clarity while maintaining the feel.
                            - If a street address is included, include **street name only** (no house number).
                            - **Do not include** home square footage or lot size.
                            - Expand any abbreviations (e.g., “ave” → “avenue”, “st” → “street”).
                            - Avoid clichéd endings like “perfect for you” or “your dream home awaits.”

                            Generate the voiceover script in {settings.OpenAI.Narration.SCRIPT_CHAR_LIMIT} characters or less
                            """
                        }]
                    },
                    {
                    "role": "user",
                    "content": [
                        {
                        "type": "text",
                        "text": f"{description}"
                        }]
                    },
                ],
                temperature=0.3,
                max_tokens=settings.OpenAI.Narration.RESPONSE_TOKEN_LIMIT,
                frequency_penalty=0,
                presence_penalty=0,
                response_format={
                    "type": "text"
                }
            )

            narration_script = response.choices[0].message.content
            
            script_len = len(narration_script)
            if script_len <= settings.OpenAI.Narration.SCRIPT_MAX_CHARACTERS:
                return narration_script
            else:
                if num_attempts > settings.OpenAI.Narration.MAX_GEN_ATTEMPTS:
                    raise Exception('Script generation - Too many attempts. Exiting')
                else:
                    logger.warning(f'Generated script exceeded char count. Allowed: {settings.OpenAI.Narration.SCRIPT_MAX_CHARACTERS}, Actual: {script_len}. Retrying')
                    num_attempts += 1
            
def main():
    parser = argparse.ArgumentParser(description='AI Script Generator')

    parser.add_argument('-f', '--file', required=True, type=str, help='Description file to generate script')
    
    args = parser.parse_args()
    with open(args.file, "r") as f:
        description = f.read()
        print(f"DESCRIPTION:\n{description}")
        script_mgr = ScriptManager()
        script = script_mgr.generate_script(description=description)
        print(f"\nSCRIPT:\n{script}\n")
        print(f"COUNT: {len(script)}")

if __name__ == '__main__':
    main()