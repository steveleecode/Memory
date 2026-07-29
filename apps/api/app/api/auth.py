import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser, create_auth_token, get_current_user
from app.core.settings import Settings, get_settings
from app.db.session import get_session
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class SignInRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=240)


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: uuid.UUID
    email: str
    display_name: str | None


class AuthUserResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None
    created_at: datetime
    updated_at: datetime


@router.post("/sign-in", response_model=AuthSessionResponse)
async def sign_in(
    request: SignInRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthSessionResponse:
    email = request.email.lower()
    if "@" not in email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "email address is required")
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, display_name=request.display_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif request.display_name and user.display_name != request.display_name:
        user.display_name = request.display_name
        await session.commit()
        await session.refresh(user)
    token = create_auth_token(user_id=user.id, email=user.email, settings=settings)
    return AuthSessionResponse(
        access_token=token,
        expires_in=settings.auth_token_ttl_seconds,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
    )


@router.get("/me", response_model=AuthUserResponse)
async def me(
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthUserResponse:
    user = (await session.execute(select(User).where(User.id == authenticated.id))).scalar_one()
    return AuthUserResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
