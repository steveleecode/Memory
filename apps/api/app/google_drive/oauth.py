import base64
import hashlib
import secrets
import time
import uuid
from urllib.parse import urlencode

from app.core.settings import Settings

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
OPENID_SCOPE = "openid"
EMAIL_SCOPE = "email"
PROFILE_SCOPE = "profile"
REQUESTED_SCOPES = (DRIVE_READONLY_SCOPE, OPENID_SCOPE, EMAIL_SCOPE, PROFILE_SCOPE)


class OAuthStateError(ValueError):
    pass


def create_oauth_state(user_id: uuid.UUID, *, ttl_seconds: int = 600) -> tuple[str, str]:
    nonce = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + ttl_seconds
    state = f"{user_id}:{expires_at}:{nonce}"
    return state, nonce


def validate_oauth_state(state: str, nonce: str) -> uuid.UUID:
    parts = state.split(":", 2)
    if len(parts) != 3:
        raise OAuthStateError("invalid OAuth state")
    user_id_raw, expires_at_raw, state_nonce = parts
    if not secrets.compare_digest(state_nonce, nonce):
        raise OAuthStateError("invalid OAuth state")
    if int(expires_at_raw) < int(time.time()):
        raise OAuthStateError("expired OAuth state")
    return uuid.UUID(user_id_raw)


def create_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def authorization_url(settings: Settings, state: str, code_challenge: str) -> str:
    query = urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_url,
            "response_type": "code",
            "scope": " ".join(REQUESTED_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
