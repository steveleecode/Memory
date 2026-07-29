import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser, get_current_user, require_matching_user
from app.core.settings import Settings, get_settings
from app.db.session import get_session
from app.google_drive.client import (
    GoogleAuthorizationError,
    GoogleDriveClient,
    HttpGoogleDriveClient,
)
from app.google_drive.crypto import decrypt_json, encrypt_json
from app.google_drive.oauth import (
    REQUESTED_SCOPES,
    OAuthStateError,
    authorization_url,
    create_oauth_state,
    create_pkce_pair,
    validate_oauth_state,
)
from app.google_drive.sync import get_drive_source, run_drive_sync
from app.models.document import Document, DocumentStatus
from app.models.source import Source, SourceKind, SourceStatus

router = APIRouter(prefix="/sources/google-drive", tags=["google-drive"])


class BeginGoogleDriveConnectionRequest(BaseModel):
    user_id: uuid.UUID | None = None


class BeginGoogleDriveConnectionResponse(BaseModel):
    authorization_url: str
    state: str
    status: SourceStatus


class GoogleDriveConnectionStatusResponse(BaseModel):
    id: uuid.UUID | None
    user_id: uuid.UUID
    kind: SourceKind = SourceKind.GOOGLE_DRIVE
    status: SourceStatus
    account_email: str | None
    account_id: str | None
    granted_scopes: list[str]
    last_successful_synchronization_time: str | None
    sync_status: str
    last_synchronization_error: str | None
    indexed_count: int
    failed_count: int
    skipped_count: int
    unchanged_count: int
    last_summary: dict[str, object] | None
    created_at: datetime | None
    updated_at: datetime | None


class SourceActionRequest(BaseModel):
    user_id: uuid.UUID | None = None


class SyncResponse(BaseModel):
    source_id: uuid.UUID
    summary: dict[str, object]


class FailureResponse(BaseModel):
    document_id: uuid.UUID
    title: str
    error: str | None
    metadata: dict[str, object]


class OpenUrlResponse(BaseModel):
    document_id: uuid.UUID
    drive_web_url: str


def google_drive_client(settings: Annotated[Settings, Depends(get_settings)]) -> GoogleDriveClient:
    return HttpGoogleDriveClient(settings)


@router.post("/oauth/start", response_model=BeginGoogleDriveConnectionResponse)
async def begin_connection(
    request: BeginGoogleDriveConnectionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> BeginGoogleDriveConnectionResponse:
    require_matching_user(authenticated, request.user_id)
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google OAuth is not configured on the backend",
        )
    state, nonce = create_oauth_state(authenticated.id)
    verifier, challenge = create_pkce_pair()
    source = Source(
        user_id=authenticated.id,
        kind=SourceKind.GOOGLE_DRIVE,
        status=SourceStatus.CONNECTING,
        external_id=f"oauth:{nonce}",
        display_name="Google Drive",
        encrypted_credentials=encrypt_json(
            {"state_nonce": nonce, "pkce_verifier": verifier, "created_at": _now()},
            settings.oauth_credential_encryption_key,
        ),
        source_metadata={
            "connection_status": "connecting",
            "requested_scopes": list(REQUESTED_SCOPES),
        },
    )
    session.add(source)
    await session.commit()
    return BeginGoogleDriveConnectionResponse(
        authorization_url=authorization_url(settings, state, challenge),
        state=state,
        status=SourceStatus.CONNECTING,
    )


@router.get("/oauth/callback")
async def oauth_callback(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[GoogleDriveClient, Depends(google_drive_client)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error:
        return _redirect(settings, {"google_drive": "error", "reason": "authorization_denied"})
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing OAuth callback parameters")
    pending_sources = (
        await session.execute(
            select(Source).where(
                Source.kind == SourceKind.GOOGLE_DRIVE,
                Source.status == SourceStatus.CONNECTING,
            )
        )
    ).scalars()
    for pending in pending_sources:
        credentials = decrypt_json(
            pending.encrypted_credentials or b"",
            settings.oauth_credential_encryption_key,
        )
        nonce = credentials.get("state_nonce")
        if not isinstance(nonce, str):
            continue
        try:
            user_id = validate_oauth_state(state, nonce)
        except (OAuthStateError, ValueError):
            continue
        if user_id != pending.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "OAuth state user mismatch")
        verifier = str(credentials["pkce_verifier"])
        token = await client.exchange_code(code, verifier)
        userinfo = await client.userinfo(token.access_token)
        account_id = str(userinfo.get("sub") or "")
        if not account_id:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google account identifier missing")
        account_email = userinfo.get("email") if isinstance(userinfo.get("email"), str) else None
        existing = (
            await session.execute(
                select(Source).where(
                    Source.user_id == user_id,
                    Source.kind == SourceKind.GOOGLE_DRIVE,
                    Source.external_id == account_id,
                )
            )
        ).scalar_one_or_none()
        source = existing or pending
        if existing and existing.id != pending.id:
            await session.delete(pending)
        refresh_token = token.refresh_token
        if refresh_token is None and existing and existing.encrypted_credentials:
            current = decrypt_json(
                existing.encrypted_credentials,
                settings.oauth_credential_encryption_key,
            )
            value = current.get("refresh_token")
            refresh_token = value if isinstance(value, str) else None
        if not refresh_token:
            source.status = SourceStatus.REAUTHORIZATION_REQUIRED
            source.source_metadata = {
                **(source.source_metadata or {}),
                "last_synchronization_error": "Google did not return a refresh token",
            }
            await session.commit()
            return _redirect(settings, {"google_drive": "reauthorization_required"})
        source.user_id = user_id
        source.kind = SourceKind.GOOGLE_DRIVE
        source.status = SourceStatus.CONNECTED
        source.external_id = account_id
        source.display_name = account_email or "Google Drive"
        source.encrypted_credentials = encrypt_json(
            {
                "refresh_token": refresh_token,
                "granted_scopes": token.scope.split(),
                "account_id": account_id,
                "account_email": account_email,
                "updated_at": _now(),
            },
            settings.oauth_credential_encryption_key,
        )
        source.source_metadata = {
            **(source.source_metadata or {}),
            "connection_status": "connected",
            "google_account_identifier": account_id,
            "google_account_email": account_email,
            "granted_scopes": token.scope.split(),
            "initial_synchronization_status": "not_started",
            "last_synchronization_error": None,
        }
        await session.commit()
        return _redirect(settings, {"google_drive": "connected", "source_id": str(source.id)})
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid OAuth state")


@router.get("/status", response_model=GoogleDriveConnectionStatusResponse)
async def read_connection_status(
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_id: uuid.UUID | None = None,
) -> GoogleDriveConnectionStatusResponse:
    require_matching_user(authenticated, user_id)
    source = (
        (
            await session.execute(
                select(Source)
                .where(Source.user_id == authenticated.id, Source.kind == SourceKind.GOOGLE_DRIVE)
                .where(Source.status != SourceStatus.CONNECTING)
                .order_by(Source.updated_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if source is None:
        return GoogleDriveConnectionStatusResponse(
            id=None,
            user_id=authenticated.id,
            status=SourceStatus.NOT_CONNECTED,
            account_email=None,
            account_id=None,
            granted_scopes=[],
            last_successful_synchronization_time=None,
            sync_status="idle",
            last_synchronization_error=None,
            indexed_count=0,
            failed_count=0,
            skipped_count=0,
            unchanged_count=0,
            last_summary=None,
            created_at=None,
            updated_at=None,
        )
    return await _status_response(session, source)


@router.post("/{source_id}/disconnect", response_model=GoogleDriveConnectionStatusResponse)
async def disconnect(
    source_id: uuid.UUID,
    request: SourceActionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[GoogleDriveClient, Depends(google_drive_client)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> GoogleDriveConnectionStatusResponse:
    require_matching_user(authenticated, request.user_id)
    source = await _source_or_404(session, authenticated.id, source_id)
    refresh_token = None
    if source.encrypted_credentials:
        credentials = decrypt_json(
            source.encrypted_credentials,
            settings.oauth_credential_encryption_key,
        )
        value = credentials.get("refresh_token")
        refresh_token = value if isinstance(value, str) else None
    if refresh_token:
        with suppress(GoogleAuthorizationError):
            await client.revoke_token(refresh_token)
    source.encrypted_credentials = None
    source.status = SourceStatus.DISCONNECTED
    source.source_metadata = {
        **(source.source_metadata or {}),
        "connection_status": "disconnected",
        "last_synchronization_error": None,
        "disconnected_at": _now(),
    }
    await session.commit()
    return await _status_response(session, source)


@router.post("/{source_id}/sync/initial", response_model=SyncResponse)
async def start_initial_sync(
    source_id: uuid.UUID,
    request: SourceActionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[GoogleDriveClient, Depends(google_drive_client)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> SyncResponse:
    require_matching_user(authenticated, request.user_id)
    return await _run_sync_endpoint(
        session,
        settings,
        client,
        authenticated.id,
        source_id,
        "initial",
    )


@router.post("/{source_id}/sync/incremental", response_model=SyncResponse)
async def start_incremental_sync(
    source_id: uuid.UUID,
    request: SourceActionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[GoogleDriveClient, Depends(google_drive_client)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> SyncResponse:
    require_matching_user(authenticated, request.user_id)
    return await _run_sync_endpoint(
        session,
        settings,
        client,
        authenticated.id,
        source_id,
        "incremental",
    )


@router.get("/{source_id}/sync/status", response_model=GoogleDriveConnectionStatusResponse)
async def read_sync_status(
    source_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_id: uuid.UUID | None = None,
) -> GoogleDriveConnectionStatusResponse:
    require_matching_user(authenticated, user_id)
    source = await _source_or_404(session, authenticated.id, source_id)
    return await _status_response(session, source)


@router.get("/{source_id}/sync/summary", response_model=dict[str, object])
async def read_sync_summary(
    source_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_id: uuid.UUID | None = None,
) -> dict[str, object]:
    require_matching_user(authenticated, user_id)
    source = await _source_or_404(session, authenticated.id, source_id)
    summary = (source.source_metadata or {}).get("last_synchronization_summary")
    return summary if isinstance(summary, dict) else {}


@router.get("/{source_id}/failures", response_model=list[FailureResponse])
async def list_failures(
    source_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_id: uuid.UUID | None = None,
) -> list[FailureResponse]:
    require_matching_user(authenticated, user_id)
    source = await _source_or_404(session, authenticated.id, source_id)
    documents = (
        await session.execute(
            select(Document).where(
                Document.user_id == authenticated.id,
                Document.source_id == source.id,
                Document.status == DocumentStatus.FAILED,
            )
        )
    ).scalars()
    return [
        FailureResponse(
            document_id=document.id,
            title=document.title,
            error=document.ingestion_error,
            metadata=document.document_metadata or {},
        )
        for document in documents
    ]


@router.post("/{source_id}/failures/{document_id}/retry", response_model=SyncResponse)
async def retry_failed_file(
    source_id: uuid.UUID,
    document_id: uuid.UUID,
    request: SourceActionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[GoogleDriveClient, Depends(google_drive_client)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> SyncResponse:
    require_matching_user(authenticated, request.user_id)
    source = await _source_or_404(session, authenticated.id, source_id)
    document = (
        await session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == authenticated.id,
                Document.source_id == source.id,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "failed Drive document not found")
    summary = await run_drive_sync(
        session=session,
        settings=settings,
        client=client,
        user_id=authenticated.id,
        source_id=source_id,
        mode="incremental",
    )
    return SyncResponse(source_id=source_id, summary=summary.to_dict())


@router.get("/documents/{document_id}/open", response_model=OpenUrlResponse)
async def open_drive_document(
    document_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_id: uuid.UUID | None = None,
) -> OpenUrlResponse:
    require_matching_user(authenticated, user_id)
    document = (
        await session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == authenticated.id,
                Document.status != DocumentStatus.DELETED,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Drive document not found")
    metadata = document.document_metadata or {}
    drive_url = metadata.get("drive_web_url")
    if not isinstance(drive_url, str) or not drive_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Drive URL not available")
    return OpenUrlResponse(document_id=document.id, drive_web_url=drive_url)


async def _run_sync_endpoint(
    session: AsyncSession,
    settings: Settings,
    client: GoogleDriveClient,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    mode: str,
) -> SyncResponse:
    try:
        summary = await run_drive_sync(
            session=session,
            settings=settings,
            client=client,
            user_id=user_id,
            source_id=source_id,
            mode="initial" if mode == "initial" else "incremental",
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return SyncResponse(source_id=source_id, summary=summary.to_dict())


async def _source_or_404(session: AsyncSession, user_id: uuid.UUID, source_id: uuid.UUID) -> Source:
    try:
        return await get_drive_source(session, user_id, source_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


async def _status_response(
    session: AsyncSession,
    source: Source,
) -> GoogleDriveConnectionStatusResponse:
    metadata = dict(source.source_metadata or {})
    indexed = await _count_documents(session, source, DocumentStatus.INDEXED)
    failed = await _count_documents(session, source, DocumentStatus.FAILED)
    summary = metadata.get("last_synchronization_summary")
    summary_dict = summary if isinstance(summary, dict) else {}
    granted_scope_values = metadata.get("granted_scopes")
    granted_scopes = (
        [str(item) for item in granted_scope_values]
        if isinstance(granted_scope_values, list)
        else []
    )
    return GoogleDriveConnectionStatusResponse(
        id=source.id,
        user_id=source.user_id,
        status=source.status,
        account_email=_string(metadata.get("google_account_email")),
        account_id=_string(metadata.get("google_account_identifier")),
        granted_scopes=granted_scopes,
        last_successful_synchronization_time=_string(
            metadata.get("last_successful_synchronization_time")
        ),
        sync_status=_string(metadata.get("sync_status")) or "idle",
        last_synchronization_error=_string(metadata.get("last_synchronization_error")),
        indexed_count=indexed,
        failed_count=failed,
        skipped_count=int(summary_dict.get("files_skipped") or 0),
        unchanged_count=int(summary_dict.get("files_unchanged") or 0),
        last_summary=summary_dict or None,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


async def _count_documents(
    session: AsyncSession,
    source: Source,
    document_status: DocumentStatus,
) -> int:
    return int(
        (
            await session.execute(
                select(func.count(Document.id)).where(
                    Document.user_id == source.user_id,
                    Document.source_id == source.id,
                    Document.status == document_status,
                )
            )
        ).scalar_one()
        or 0
    )


def _redirect(settings: Settings, params: dict[str, str]) -> RedirectResponse:
    separator = "&" if "?" in settings.google_oauth_frontend_return_url else "?"
    return RedirectResponse(
        f"{settings.google_oauth_frontend_return_url}{separator}{urlencode(params)}"
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
