from typing import Optional
from pydantic import BaseModel

class UserInfo(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
