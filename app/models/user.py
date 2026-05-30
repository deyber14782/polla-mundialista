from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum

class UserRole(str, Enum):
    admin = "admin"
    player = "player"

class UserCreate(BaseModel):
    email: EmailStr
    display_name: str
    phone: str
    photo_url: Optional[str] = None

class UserResponse(BaseModel):
    uid: str
    email: str
    display_name: str
    phone: str
    photo_url: Optional[str] = None
    role: UserRole = UserRole.player
    total_score: int = 0
    predictions_count: int = 0
    exact_results: int = 0