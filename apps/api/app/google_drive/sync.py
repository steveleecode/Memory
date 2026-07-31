import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.google_drive.client import (
    GoogleAuthorizationError,
    GoogleDriveClient,
    GooglePermanentError,
    GoogleRateLimitError,
    GoogleTransientError,
)
from app.google_drive.crypto import decrypt_json, encrypt_json
from app.google_drive.mime import ContentPlan, content_filename, content_plan
from app.ingestion.embeddings import EmbeddingProvider, GeminiEmbeddingProvider
from app.ingestion.hashing import sha256_bytes
from app.ingestion.pipeline import ingest_document_content
from app.models.document import Document, DocumentChunk, DocumentStatus, SearchRepresentation
from app.models.source import Source, SourceKind, SourceStatus

SyncMode = Literal["initial", "incremental"]


@dataclass
class SyncSummary:
    source_id: uuid.UUID
    mode: SyncMode
    files_discovered: int = 0
    files_supported: int = 0
    files_indexed: int = 0
    files_unchanged: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    files_deleted_or_removed: int = 0
    duration_seconds: float = 0.0
    additional_work_remains: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": str(self.source_id),
            "mode": self.mode,
            "files_discovered": self.files_discovered,
            "files_supported": self.files_supported,
            "files_indexed": self.files_indexed,
            "files_unchanged": self.files_unchanged,
            "files_skipped": self.files_skipped,
            "files_failed": self.files_failed,
            "files_deleted_or_removed": self.files_deleted_or_removed,
            "duration_seconds": round(self.duration_seconds, 3),
            "additional_work_remains": self.additional_work_remains,
        }


async def run_drive_sync(
    *,
    session: AsyncSession,
    settings: Settings,
    client: GoogleDriveClient,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    mode: SyncMode,
    embedding_provider: EmbeddingProvider | None = None,
) -> SyncSummary:
    source = await get_drive_source(session, user_id, source_id)
    metadata = dict(source.source_metadata or {})
    if metadata.get("sync_status") == "running":
        raise RuntimeError("a Google Drive synchronization is already running for this source")
    summary = SyncSummary(source_id=source.id, mode=mode)
    started = time.monotonic()
    previous_status = source.status
    source.status = SourceStatus.SYNCING
    source.source_metadata = {
        **metadata,
        "sync_status": "running",
        "sync_started_at": _now(),
        "last_synchronization_error": None,
    }
    await session.commit()

    try:
        access_token = await refresh_access_token(session, settings, client, source)
        provider = embedding_provider or GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        if mode == "initial" or not source.sync_cursor:
            await _initial_sync(
                session=session,
                settings=settings,
                client=client,
                source=source,
                access_token=access_token,
                provider=provider,
                summary=summary,
            )
        else:
            await _incremental_sync(
                session=session,
                settings=settings,
                client=client,
                source=source,
                access_token=access_token,
                provider=provider,
                summary=summary,
            )
        summary.duration_seconds = time.monotonic() - started
        await _finish_sync(session, source, summary, SourceStatus.CONNECTED)
    except GoogleAuthorizationError as exc:
        summary.duration_seconds = time.monotonic() - started
        await _fail_sync(session, source, summary, SourceStatus.REAUTHORIZATION_REQUIRED, str(exc))
    except Exception as exc:
        summary.duration_seconds = time.monotonic() - started
        await _fail_sync(session, source, summary, SourceStatus.ERROR, _public_error(exc))
        if isinstance(exc, RuntimeError) and "already running" in str(exc):
            source.status = previous_status
        raise
    return summary


async def refresh_access_token(
    session: AsyncSession,
    settings: Settings,
    client: GoogleDriveClient,
    source: Source,
) -> str:
    if not source.encrypted_credentials:
        raise GoogleAuthorizationError("Google Drive connection requires reauthorization")
    credentials = decrypt_json(
        source.encrypted_credentials,
        settings.oauth_credential_encryption_key,
    )
    refresh_token = credentials.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise GoogleAuthorizationError("Google Drive refresh token is missing")
    response = await client.refresh_access_token(refresh_token)
    updated = {
        **credentials,
        "refresh_token": response.refresh_token or refresh_token,
        "granted_scopes": response.scope.split(),
        "updated_at": _now(),
    }
    source.encrypted_credentials = encrypt_json(
        updated,
        settings.oauth_credential_encryption_key,
    )
    source.source_metadata = {
        **(source.source_metadata or {}),
        "granted_scopes": response.scope.split(),
    }
    await session.commit()
    return response.access_token


async def get_drive_source(
    session: AsyncSession,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
) -> Source:
    source = (
        await session.execute(
            select(Source).where(
                Source.id == source_id,
                Source.user_id == user_id,
                Source.kind == SourceKind.GOOGLE_DRIVE,
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise LookupError("Google Drive source not found")
    return source


async def _initial_sync(
    *,
    session: AsyncSession,
    settings: Settings,
    client: GoogleDriveClient,
    source: Source,
    access_token: str,
    provider: EmbeddingProvider,
    summary: SyncSummary,
) -> None:
    start_cursor = await client.start_page_token(access_token)
    async for file_metadata in client.list_files(access_token):
        await _process_file(
            session=session,
            settings=settings,
            client=client,
            source=source,
            access_token=access_token,
            provider=provider,
            file_metadata=file_metadata,
            summary=summary,
        )
    source.sync_cursor = start_cursor
    await session.commit()


async def _incremental_sync(
    *,
    session: AsyncSession,
    settings: Settings,
    client: GoogleDriveClient,
    source: Source,
    access_token: str,
    provider: EmbeddingProvider,
    summary: SyncSummary,
) -> None:
    assert source.sync_cursor is not None
    next_cursor: str | None = None
    async for change, _next_page, new_start in client.list_changes(
        access_token,
        source.sync_cursor,
    ):
        file_id = _string(change.get("fileId"))
        file_metadata = change.get("file") if isinstance(change.get("file"), dict) else None
        if change.get("removed") is True and file_id:
            await _mark_removed(session, source, file_id, summary)
            continue
        if file_metadata is None:
            if file_id:
                await _mark_removed(session, source, file_id, summary)
            continue
        await _process_file(
            session=session,
            settings=settings,
            client=client,
            source=source,
            access_token=access_token,
            provider=provider,
            file_metadata=file_metadata,
            summary=summary,
        )
        if new_start:
            next_cursor = new_start
    if next_cursor:
        source.sync_cursor = next_cursor
    await session.commit()


async def _process_file(
    *,
    session: AsyncSession,
    settings: Settings,
    client: GoogleDriveClient,
    source: Source,
    access_token: str,
    provider: EmbeddingProvider,
    file_metadata: dict[str, Any],
    summary: SyncSummary,
) -> None:
    summary.files_discovered += 1
    file_id = str(file_metadata.get("id") or "")
    filename = str(file_metadata.get("name") or file_id or "Untitled")
    if not file_id:
        summary.files_failed += 1
        return
    if file_metadata.get("trashed") is True:
        await _mark_removed(session, source, file_id, summary)
        return

    plan = content_plan(filename, _string(file_metadata.get("mimeType")))
    document = await _upsert_document(session, source, file_metadata, plan)
    if not plan.supported:
        summary.files_skipped += 1
        document.status = DocumentStatus.FAILED
        document.ingestion_error = plan.reason
        document.document_metadata = {
            **(document.document_metadata or {}),
            "indexing_status": "unsupported",
        }
        await session.commit()
        return

    summary.files_supported += 1
    try:
        content = await _fetch_content(client, access_token, file_id, file_metadata, plan)
        digest = sha256_bytes(content)
        document.content_hash = digest
        document.document_metadata = {
            **(document.document_metadata or {}),
            "content_hash": digest,
            "indexing_status": "unchanged"
            if document.indexed_content_hash == digest and document.status == DocumentStatus.INDEXED
            else "indexing",
        }
        await session.commit()
        if document.indexed_content_hash == digest and document.status == DocumentStatus.INDEXED:
            summary.files_unchanged += 1
            return
        job = await ingest_document_content(
            session=session,
            settings=settings,
            embedding_provider=provider,
            document_id=document.id,
            filename=content_filename(filename, plan),
            content=content,
            mime_type=plan.ingest_mime_type,
        )
        await session.refresh(document)
        if str(job.status) == "succeeded":
            summary.files_indexed += 1
        elif str(job.status) == "skipped":
            summary.files_unchanged += 1
        else:
            summary.files_failed += 1
    except (GoogleRateLimitError, GoogleTransientError):
        summary.files_failed += 1
        await _record_file_failure(session, document, "temporary_google_error")
    except GooglePermanentError as exc:
        summary.files_failed += 1
        await _record_file_failure(session, document, _public_error(exc))


async def _fetch_content(
    client: GoogleDriveClient,
    access_token: str,
    file_id: str,
    file_metadata: dict[str, Any],
    plan: ContentPlan,
) -> bytes:
    if plan.action == "export" and plan.ingest_mime_type:
        return await client.export_file(access_token, file_id, plan.ingest_mime_type)
    if plan.action == "download":
        return await client.download_file(access_token, file_id)
    lines = [
        f"Filename: {file_metadata.get('name')}",
        f"Mime type: {file_metadata.get('mimeType')}",
        f"Modified time: {file_metadata.get('modifiedTime')}",
        f"Drive URL: {file_metadata.get('webViewLink')}",
    ]
    return "\n".join(line for line in lines if line.split(": ", 1)[-1] not in {"None", ""}).encode(
        "utf-8"
    )


async def _upsert_document(
    session: AsyncSession,
    source: Source,
    file_metadata: dict[str, Any],
    plan: ContentPlan,
) -> Document:
    file_id = str(file_metadata["id"])
    document = (
        await session.execute(
            select(Document).where(
                Document.user_id == source.user_id,
                Document.source_id == source.id,
                Document.external_id == file_id,
            )
        )
    ).scalar_one_or_none()
    document = document or Document(
        user_id=source.user_id,
        source_id=source.id,
        external_id=file_id,
        document_metadata={},
    )
    document.title = str(file_metadata.get("name") or file_id)
    document.mime_type = plan.ingest_mime_type or _string(file_metadata.get("mimeType"))
    if document.status == DocumentStatus.DELETED:
        document.status = DocumentStatus.DISCOVERED
    document.ingestion_error = None
    document.document_metadata = {
        **(document.document_metadata or {}),
        "google_drive_file_id": file_id,
        "filename": document.title,
        "source_id": str(source.id),
        "source_type": "google_drive",
        "drive_mime_type": _string(file_metadata.get("mimeType")),
        "parents": _string_list(file_metadata.get("parents")),
        "created_time": _string(file_metadata.get("createdTime")),
        "modified_time": _string(file_metadata.get("modifiedTime")),
        "size": _int_string(file_metadata.get("size")),
        "checksum": _string(file_metadata.get("md5Checksum")),
        "drive_web_url": _string(file_metadata.get("webViewLink")),
        "trashed": bool(file_metadata.get("trashed") is True),
        "owned_by_me": bool(file_metadata.get("ownedByMe") is True),
        "shared": bool(file_metadata.get("shared") is True),
        "version": _string(file_metadata.get("version")),
        "head_revision_id": _string(file_metadata.get("headRevisionId")),
        "supported": plan.supported,
        "sync_seen_at": _now(),
    }
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def _mark_removed(
    session: AsyncSession,
    source: Source,
    file_id: str,
    summary: SyncSummary,
) -> None:
    document = (
        await session.execute(
            select(Document).where(
                Document.user_id == source.user_id,
                Document.source_id == source.id,
                Document.external_id == file_id,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        return
    document.status = DocumentStatus.DELETED
    document.document_metadata = {
        **(document.document_metadata or {}),
        "indexing_status": "deleted",
        "deleted_at": _now(),
    }
    document.embedding = None
    document.searchable_text = None
    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    await session.execute(
        delete(SearchRepresentation).where(SearchRepresentation.document_id == document.id)
    )
    summary.files_deleted_or_removed += 1
    await session.commit()


async def _record_file_failure(session: AsyncSession, document: Document, message: str) -> None:
    document.status = DocumentStatus.FAILED
    document.ingestion_error = message
    document.document_metadata = {
        **(document.document_metadata or {}),
        "indexing_status": "failed",
    }
    await session.commit()


async def _finish_sync(
    session: AsyncSession,
    source: Source,
    summary: SyncSummary,
    status: SourceStatus,
) -> None:
    source.status = status
    source.source_metadata = {
        **(source.source_metadata or {}),
        "sync_status": "idle",
        "initial_synchronization_status": "complete",
        "last_successful_synchronization_time": _now(),
        "last_synchronization_error": None,
        "last_synchronization_summary": summary.to_dict(),
    }
    await session.commit()


async def _fail_sync(
    session: AsyncSession,
    source: Source,
    summary: SyncSummary,
    status: SourceStatus,
    message: str,
) -> None:
    source.status = status
    source.source_metadata = {
        **(source.source_metadata or {}),
        "sync_status": "idle",
        "last_synchronization_error": message,
        "last_synchronization_summary": summary.to_dict(),
    }
    await session.commit()


def _public_error(exc: Exception) -> str:
    return str(exc).splitlines()[0][:500]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _int_string(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
