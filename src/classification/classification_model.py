from pydantic import BaseModel, Field, field_serializer
from typing import Dict, List, Tuple, Optional
from enum import Enum

class HeroSelectionEnum(str, Enum):
    FILENAME = 'Filename' # Choose 1st image based on lexicographic sorting
    HIGH_SCORE = 'High_Score' # Image with the highest score based on the category rankings for the 1st image
    CUSTOM = 'Custom' # Custom function to select image
    
class RealEstate(BaseModel):
    categories:list[str] = Field(..., description='All the categories relevant to real estate images')
    hero_image: bool = Field(default=True, description='If true, the 1st image is the `hero` image')
    hero_selection: HeroSelectionEnum = Field(default=HeroSelectionEnum.FILENAME, description='Hero image selection mechanism')
    boundary_priorities_small:Dict[int, List[str]] = Field(..., description='Boundary priority for small video (<10 clips)')
    boundary_priorities_large:Dict[int, List[str]] = Field(..., description='Boundary clip suggestions for large video (>=10 clips)')
    interior_order:List[str] = Field(..., description='Order for non-special clips')
    
    @field_serializer("boundary_priorities_small", "boundary_priorities_large")
    def serialize_boundary_priorities(self, value: Dict[int, List[str]]) -> Dict[str, List[str]]:
        # Convert integer keys to strings at serialization time
        return {str(k): v for k, v in value.items()}
    
class ImageBuckets(BaseModel):
    class ImageInfo(BaseModel):
        class Label(BaseModel):
            score:str = Field(..., description='Probability/Confidence score of a particular feature in the image')
            description:str = Field(..., description='Description of the label')
        category: str = Field(..., description='Category of the image computed from the features')
        uri:str = Field(..., description='File path of the image')
        labels:list[Label] = Field(..., description='List of features for an image')
        score:int = Field(..., description='Image `score` - Count of all features detected for image by vision API')
        
    class Item(BaseModel):
        uri:str = Field(..., description='File path of the image')
        score:int = Field(..., description='Image `score` - Count of all features detected for image by vision API')
    
    buckets:Dict[str, List[Item]] = Field(default={}, description='Images bucketed into categories')

class ImageSequence(BaseModel):
    class ImageInfo(BaseModel):
        uri: str = Field(..., description='URI of the image')
        category: str = Field(..., description='Image category')
        rationale: str = Field(..., description='Rationale behind image selection')
        score: int = Field(..., description='Image score')
        
    sequence : list[ImageInfo] = Field(..., description='Ordered sequence of images used to make movie')
    

    