from pydantic import BaseModel, field_serializer
from pathlib import Path
from urllib.parse import urlparse

class CloudPath(BaseModel):
        bucket_id: str
        path: Path
      
        def full_path(self)->str:
            return f'gs://{self.bucket_id}/{self.path}'
        
        @staticmethod
        def from_path(path:str)->'CloudPath':
            # Parse the GCS path
            parsed_url = urlparse(path)
            if parsed_url.scheme != 'gs':
                raise ValueError("Invalid GCS path. It should start with 'gs://'")
            
            bucket_id = parsed_url.netloc
            prefix = parsed_url.path.lstrip('/')  # Remove leading '/'
            
            return CloudPath(bucket_id=bucket_id, path=Path(prefix))
            
              
        @field_serializer('path')
        def serialize_path(self, path: Path) -> str:
            return str(path)
