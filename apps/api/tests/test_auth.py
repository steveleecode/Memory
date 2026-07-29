import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticationError, create_auth_token, verify_auth_token
from app.core.settings import Settings
from app.main import create_app


def test_auth_token_round_trips_user_identity() -> None:
    settings = Settings(MEMORY_AUTH_TOKEN_SECRET="test-secret", MEMORY_AUTH_TOKEN_TTL_SECONDS=60)
    user_id = uuid.uuid4()

    token = create_auth_token(user_id=user_id, email="user@example.com", settings=settings, now=100)
    payload = verify_auth_token(token, "test-secret", now=120)

    assert payload["sub"] == str(user_id)
    assert payload["email"] == "user@example.com"


def test_auth_token_rejects_wrong_secret() -> None:
    settings = Settings(MEMORY_AUTH_TOKEN_SECRET="test-secret", MEMORY_AUTH_TOKEN_TTL_SECONDS=60)
    token = create_auth_token(
        user_id=uuid.uuid4(),
        email="user@example.com",
        settings=settings,
        now=100,
    )

    with pytest.raises(AuthenticationError):
        verify_auth_token(token, "wrong-secret", now=120)


def test_auth_token_expires() -> None:
    settings = Settings(MEMORY_AUTH_TOKEN_SECRET="test-secret", MEMORY_AUTH_TOKEN_TTL_SECONDS=60)
    token = create_auth_token(
        user_id=uuid.uuid4(),
        email="user@example.com",
        settings=settings,
        now=100,
    )

    with pytest.raises(AuthenticationError):
        verify_auth_token(token, "test-secret", now=161)


def test_protected_search_requires_bearer_token() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/search", json={"query": "memory"})

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication required"
