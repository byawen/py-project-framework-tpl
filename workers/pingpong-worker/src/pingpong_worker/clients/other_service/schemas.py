from pydantic import BaseModel


class UserInfo(BaseModel):
    user_id: str
    name: str
    email: str | None = None
