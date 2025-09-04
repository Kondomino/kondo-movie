from pydantic import BaseModel, EmailStr
from typing import Optional, ClassVar
from rich import print

class UserInfo(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
class Shuffle(BaseModel):
    last_used_music_rank: Optional[int] = 0
    last_used_voice_rank: Optional[int] = 0

class UserData(BaseModel):
    REMIX_KEY:ClassVar[str] = 'remix'
    
    id: str
    user_info: Optional[UserInfo] = None
    subscription_id: Optional[str] = ""
    device_token: Optional[str] = ""
    is_deleted: bool = False
    agreed_to_terms: bool = False
    remix: Optional[Shuffle] = Shuffle()
    tenant_id: Optional[str] = None  # Default to None for backward compatibility
    portal_ready: bool = True  # Default to True for backward compatibility
    welcome_email_sent: Optional[bool] = True # Default to True for backward compatibility
    portal_ready_email_sent: Optional[bool] = True # Default to True for backward compatibility


def main():
    user_data = UserData(
        id = '12345',
        user_info=UserInfo(
            email='john@gmail.com',
            first_name='John',
            last_name='Doe'
        ),
        subscription_id='123',
        device_token='123',
        is_deleted=False,
        agreed_to_terms=True
    )
    print(user_data.model_dump())
    
    

if __name__ == '__main__':
    main()