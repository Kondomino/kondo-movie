from typing import List, Optional, ClassVar
from pydantic import BaseModel, Field, AnyUrl, field_serializer
from datetime import datetime

class ElevenLabs(BaseModel):
    DOC_ID: ClassVar[str] = 'ElevenLabs'
    
    class Mapping(BaseModel):
        id: str = Field(..., description='11Labs Voice ID')
        eleven_labs_name: str = Field(..., description='11Labs voice name')
        editora_name: str = Field(..., description='Editora voice name')
        description: str = Field(..., description='Voice description')
        sample_audio_uri: AnyUrl = Field(..., description='Sample audio of the voice')
        rank: int = Field(..., description='Rank / Priority of the voice')
        
        @field_serializer('sample_audio_uri')
        def serialize_anyurl(self, url: AnyUrl) -> str:
            return str(url)
    
    class VersionInfo(BaseModel):
        version: int = Field(..., description='Version number of the voice mappings')
        created_at: datetime = Field(default_factory=lambda: datetime.now(), description='When this version was created')
        is_active: bool = Field(default=True, description='Whether this version is currently active')
        
    voice_mappings: List[Mapping] = Field(..., description='Mappings of all the voices used in voiceover')
    version_info: VersionInfo = Field(..., description='Version information for this set of voice mappings')
    
    @classmethod
    def get_doc_id(cls, version: Optional[int] = None) -> str:
        """
        Get the document ID for a specific version or the latest version.
        If version is None, returns the base document ID.
        """
        if version is None:
            return cls.DOC_ID
        return f"{cls.DOC_ID}_v{version}"