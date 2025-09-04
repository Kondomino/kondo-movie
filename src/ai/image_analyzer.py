import io
import os

import pillow_avif
from pillow_heif import register_heif_opener
from PIL import Image, ImageOps

from openai import OpenAI
from google.oauth2 import service_account
from google.cloud import vision

from logger import logger
from config.config import settings
from gcp.secret import secret_mgr

register_heif_opener()

VISION_SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'

class ImageAnalyzer():
    def __init__(self):
        self.openai_client = OpenAI(api_key=secret_mgr.secret(settings.Secret.OPENAI_API_KEY))
        
        cred = service_account.Credentials.from_service_account_file(VISION_SERVICE_ACCOUNT_KEY_FILE_PATH) \
            if os.path.exists(VISION_SERVICE_ACCOUNT_KEY_FILE_PATH) \
                else None
        self.vision_client = vision.ImageAnnotatorClient(
            credentials=cred
        )
        
    def labels(self, response: vision.AnnotateImageResponse)->list[dict]:

        image_labels = []
        for label in response.label_annotations:
            image_labels.append(
                {
                    'score':f"{label.score:4.0%}",
                    'description':f"{label.description:5}"
                }
            )
            
        return image_labels
    
    def analyze_image_from_uri(
        self,
        image_file_path: str,
        num_features: int
    ) -> vision.AnnotateImageResponse:

        features = [vision.Feature.Type.LABEL_DETECTION]
        
        with Image.open(image_file_path) as img:
            # Apply EXIF transpose to ensure correct orientation
            ImageOps.exif_transpose(img, in_place=True)
            
            # Convert to RGB if
            # 1. If it's AVIF or HEIF, convert to RGB for compatibility
            # 2. Format is RGBA
            if img.format in ["AVIF", "HEIF"] or img.mode == 'RGBA':
                img = img.convert("RGB")
        
            # Write to a BytesIO buffer in the desired format
            buf = io.BytesIO()
            img.save(buf, format=settings.Classification.IMAGE_FORMAT)
            buf.seek(0)
        
            image = vision.Image(content=buf.read())
            features = [vision.Feature(type_=feature_type, max_results=num_features) for feature_type in features]
            request = vision.AnnotateImageRequest(image=image, features=features)

            response = self.vision_client.annotate_image(request=request)

            return response
        
    def categorize_image(self, categories:list, image_labels:list)->str:
        try:
            response = self.openai_client.chat.completions.create(
                model=settings.OpenAI.Classification.CHAT_MODEL,
                messages=[
                    {
                        "role": "system", 
                        "content": [{
                            "type": "text",
                            "text": f"""
                                    You are a classification assistant. You are provided with a list of categories {categories}
                                    and a list of labels provided by the user describing an image.
                                    Your task is to read and understand the list of features and determine which single category best fits the image.
                                    Respond with only the category name, and no additional commentary.
                                    
                                    Based on the above categories and image labels, which single category best fits this image? 
                                    Return only the category name. The response must be one of the categories in the list provided. 
                                    """    
                        }]
                    },
                    {
                        "role": "user",
                        "content": [{
                            "type": "text",
                            "text": f"image labels : {image_labels}"
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

            return response.choices[0].message.content.rstrip()

        except Exception as e:
            logger.exception(f"An error occurred: {e}")
            raise e