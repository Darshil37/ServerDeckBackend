import datetime
from pydantic import BaseModel, EmailStr
from uuid import UUID


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    team_id: UUID
    role: str

    model_config = {"from_attributes": True}


class UserInviteCreate(BaseModel):
    email: EmailStr
    role: str = "member"


class UserDirectCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "member"


class UserAcceptInvite(BaseModel):
    token: str
    name: str
    password: str


class UserManagementResponse(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
