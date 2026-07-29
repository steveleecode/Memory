import time
import uuid

import pytest

from app.google_drive.client import (
    GoogleAuthorizationError,
    GooglePermanentError,
    _raise_google_error,
)
from app.google_drive.crypto import decrypt_json, encrypt_json
from app.google_drive.mime import (
    CSV,
    DOCX,
    GOOGLE_DOC,
    GOOGLE_SHEETS,
    PDF,
    content_filename,
    content_plan,
)
from app.google_drive.oauth import (
    OAuthStateError,
    create_oauth_state,
    create_pkce_pair,
    validate_oauth_state,
)


def test_oauth_state_round_trip_and_invalid_nonce_rejected() -> None:
    user_id = uuid.uuid4()
    state, nonce = create_oauth_state(user_id)

    assert validate_oauth_state(state, nonce) == user_id
    with pytest.raises(OAuthStateError):
        validate_oauth_state(state, "wrong")


def test_expired_oauth_state_rejected() -> None:
    user_id = uuid.uuid4()
    expired_state = f"{user_id}:{int(time.time()) - 1}:nonce"

    with pytest.raises(OAuthStateError):
        validate_oauth_state(expired_state, "nonce")


def test_pkce_pair_uses_s256_challenge() -> None:
    verifier, challenge = create_pkce_pair()

    assert len(verifier) >= 43
    assert "=" not in challenge
    assert challenge != verifier


def test_credentials_encrypt_without_plaintext_token() -> None:
    key = "test-encryption-key"
    payload = {"refresh_token": "refresh-secret", "account_email": "user@example.com"}

    ciphertext = encrypt_json(payload, key)

    assert b"refresh-secret" not in ciphertext
    assert decrypt_json(ciphertext, key) == payload


def test_google_native_export_mapping() -> None:
    doc_plan = content_plan("Project plan", GOOGLE_DOC)
    sheet_plan = content_plan("Metrics", GOOGLE_SHEETS)

    assert doc_plan.action == "export"
    assert doc_plan.ingest_mime_type == DOCX
    assert content_filename("Project plan", doc_plan).endswith(".docx")
    assert sheet_plan.ingest_mime_type == CSV


def test_uploaded_pdf_and_source_code_are_downloaded() -> None:
    assert content_plan("brief.pdf", PDF).action == "download"
    code_plan = content_plan("worker.ts", None)

    assert code_plan.supported is True
    assert code_plan.action == "download"


def test_unsupported_type_is_not_marked_supported() -> None:
    plan = content_plan("archive.zip", "application/zip")

    assert plan.supported is False
    assert plan.reason


def test_google_error_classification() -> None:
    import httpx

    with pytest.raises(GoogleAuthorizationError):
        _raise_google_error(httpx.Response(401))
    with pytest.raises(GooglePermanentError):
        _raise_google_error(httpx.Response(404))
