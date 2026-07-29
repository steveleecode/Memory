import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.settings import Settings, get_settings
from app.db.session import get_session
from app.models.user import User


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str


class AuthenticationError(ValueError):
    pass


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.authenticated_user_id = None
        request.state.authenticated_user_email = None
        authorization = request.headers.get("authorization")
        if authorization and authorization.lower().startswith("bearer "):
            settings = get_settings()
            try:
                payload = verify_auth_token(
                    authorization.removeprefix("Bearer ").removeprefix("bearer "),
                    settings.auth_token_secret,
                )
                request.state.authenticated_user_id = uuid.UUID(str(payload["sub"]))
                request.state.authenticated_user_email = str(payload["email"])
            except (AuthenticationError, ValueError, KeyError):
                request.state.authenticated_user_id = None
                request.state.authenticated_user_email = None
        return await call_next(request)


def create_auth_token(
    *,
    user_id: uuid.UUID,
    email: str,
    settings: Settings,
    now: int | None = None,
) -> str:
    issued_at = int(time.time()) if now is None else now
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": issued_at,
        "exp": issued_at + settings.auth_token_ttl_seconds,
    }
    encoded_payload = _b64_json(payload)
    signature = _signature(encoded_payload, settings.auth_token_secret)
    return f"mem1.{encoded_payload}.{signature}"


def verify_auth_token(token: str, secret: str, *, now: int | None = None) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "mem1":
        raise AuthenticationError("invalid token")
    encoded_payload, signature = parts[1], parts[2]
    expected = _signature(encoded_payload, secret)
    if not hmac.compare_digest(signature, expected):
        raise AuthenticationError("invalid token")
    payload = json.loads(_b64_decode(encoded_payload).decode("utf-8"))
    if not isinstance(payload, dict):
        raise AuthenticationError("invalid token")
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < (int(time.time()) if now is None else now):
        raise AuthenticationError("expired token")
    return payload


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthenticatedUser:
    user_id = getattr(request.state, "authenticated_user_id", None)
    if not isinstance(user_id, uuid.UUID):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authenticated user not found")
    return AuthenticatedUser(id=user.id, email=user.email)


def require_matching_user(
    authenticated: AuthenticatedUser,
    requested_user_id: uuid.UUID | None,
) -> None:
    if requested_user_id is not None and requested_user_id != authenticated.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "request user does not match token subject")


def _signature(encoded_payload: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64_encode(digest)


def _b64_json(payload: dict[str, Any]) -> str:
    return _b64_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
