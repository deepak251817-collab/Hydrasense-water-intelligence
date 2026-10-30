from typing import Optional
from pydantic import BaseModel
from app.models.user import UserRole
from app.schemas.user import UserResponse


class UserRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: UserRole = UserRole.PRODUCT_USER
    product_code: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: str
    password: str


class DeviceNumberLoginRequest(BaseModel):
    """Personal-user login by the unique number printed on the device.

    The number identifies the *device*; its bound account receives the token.
    Unbound devices must first be claimed through the normal e-mail/password
    registration + activation flow, so a printed number alone cannot create or
    hijack an account.
    """

    device_number: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user: UserResponse
