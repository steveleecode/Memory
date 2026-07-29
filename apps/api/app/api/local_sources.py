import base64
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser, get_current_user, require_matching_user
from app.core.settings import Settings, get_settings
from app.db.session import get_session
from app.ingestion.embeddings import GeminiEmbeddingProvider
from app.ingestion.hashing import sha256_bytes
from app.ingestion.pipeline import ingest_document_content
from app.models.document import Document, DocumentChunk, DocumentRelationship, DocumentStatus
from app.models.source import Source, SourceKind, SourceStatus

router = APIRouter(prefix="/sources/local-folders", tags=["local-folders"])


class LocalSourceRegisterRequest(BaseModel):
    user_id: uuid.UUID
    display_name: str = Field(min_length=1, max_length=512)
    root_fingerprint: str = Field(min_length=8, max_length=128)
    platform: str = Field(min_length=1, max_length=64)
    status: SourceStatus = SourceStatus.ACTIVE
    scan_status: str = "idle"
    watcher_status: str = "stopped"


class LocalSourceResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    kind: SourceKind
    status: SourceStatus
    display_name: str
    platform: str | None
    scan_status: str
    watcher_status: str
    last_successful_scan: str | None
    last_detected_event: str | None
    last_synchronization_error: str | None
    file_count: int
    indexed_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime


class LocalFileIngestRequest(BaseModel):
    user_id: uuid.UUID
    source_id: uuid.UUID
    relative_path: str = Field(min_length=1, max_length=2048)
    filename: str = Field(min_length=1, max_length=1024)
    mime_type: str | None = Field(default=None, max_length=255)
    size: int = Field(ge=0)
    modified_time: str | None = None
    created_time: str | None = None
    parent_directory: str | None = None
    platform_file_id: str | None = None
    content_hash: str = Field(min_length=64, max_length=128)
    content_base64: str
    metadata_only: bool = False


class LocalFileIngestResponse(BaseModel):
    document_id: uuid.UUID
    status: DocumentStatus
    indexing_status: str
    skipped: bool
    content_hash: str


class LocalDeleteRequest(BaseModel):
    user_id: uuid.UUID
    source_id: uuid.UUID
    relative_path: str = Field(min_length=1, max_length=2048)
    platform_file_id: str | None = None
    recursive: bool = False


class LocalDeleteResponse(BaseModel):
    document_id: uuid.UUID | None
    status: str


class LocalSourceStatsRequest(BaseModel):
    user_id: uuid.UUID
    source_id: uuid.UUID
    scan_status: str | None = None
    watcher_status: str | None = None
    last_detected_event: str | None = None
    last_synchronization_error: str | None = None
    last_successful_scan: str | None = None


@router.post("", response_model=LocalSourceResponse, status_code=status.HTTP_201_CREATED)
async def register_local_source(
    request: LocalSourceRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> LocalSourceResponse:
    require_matching_user(authenticated, request.user_id)
    existing = (
        await session.execute(
            select(Source).where(
                Source.user_id == request.user_id,
                Source.kind == SourceKind.LOCAL_FOLDER,
                Source.external_id == request.root_fingerprint,
            )
        )
    ).scalar_one_or_none()
    source = existing or Source(
        user_id=request.user_id,
        kind=SourceKind.LOCAL_FOLDER,
        external_id=request.root_fingerprint,
        source_metadata={},
    )
    source.display_name = request.display_name
    source.status = request.status
    source.source_metadata = {
        **(source.source_metadata or {}),
        "platform": request.platform,
        "scan_status": request.scan_status,
        "watcher_status": request.watcher_status,
        "file_count": (source.source_metadata or {}).get("file_count", 0),
        "indexed_count": (source.source_metadata or {}).get("indexed_count", 0),
        "failed_count": (source.source_metadata or {}).get("failed_count", 0),
    }
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return await _source_response(session, source)


@router.get("", response_model=list[LocalSourceResponse])
async def list_local_sources(
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_id: uuid.UUID | None = None,
) -> list[LocalSourceResponse]:
    require_matching_user(authenticated, user_id)
    sources = (
        await session.execute(
            select(Source)
            .where(Source.user_id == authenticated.id, Source.kind == SourceKind.LOCAL_FOLDER)
            .order_by(Source.created_at.desc())
        )
    ).scalars()
    return [await _source_response(session, source) for source in sources]


@router.post("/{source_id}/files", response_model=LocalFileIngestResponse)
async def ingest_local_file(
    source_id: uuid.UUID,
    request: LocalFileIngestRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> LocalFileIngestResponse:
    require_matching_user(authenticated, request.user_id)
    if source_id != request.source_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source_id mismatch")
    source = await _get_source(session, request.user_id, source_id)
    content = base64.b64decode(request.content_base64, validate=True)
    if len(content) > settings.local_max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file exceeds upload limit")
    if sha256_bytes(content) != request.content_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "content_hash mismatch")
    if len(content) != request.size:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "size mismatch")

    external_id = _local_external_id(request.relative_path, request.platform_file_id)
    lookup_clauses = [
        Document.external_id == external_id,
        Document.external_id == request.relative_path,
    ]
    document = (
        await session.execute(
            select(Document).where(
                Document.user_id == request.user_id,
                Document.source_id == source.id,
                or_(*lookup_clauses),
            )
        )
    ).scalar_one_or_none()
    if document is None and request.platform_file_id:
        document = (
            await session.execute(
                select(Document).where(
                    Document.user_id == request.user_id,
                    Document.source_id == source.id,
                    Document.document_metadata["platform_file_id"].astext
                    == request.platform_file_id,
                )
            )
        ).scalar_one_or_none()
    if document is None:
        document = (
            await session.execute(
                select(Document).where(
                    Document.user_id == request.user_id,
                    Document.source_id == source.id,
                    Document.document_metadata["relative_path"].astext == request.relative_path,
                )
            )
        ).scalar_one_or_none()
    document = document or Document(
        user_id=request.user_id,
        source_id=source.id,
        external_id=external_id,
        document_metadata={},
    )
    document.title = request.filename
    document.mime_type = request.mime_type
    document.content_hash = request.content_hash
    content_is_unchanged = (
        document.status == DocumentStatus.INDEXED
        and document.indexed_content_hash == request.content_hash
    )
    if not content_is_unchanged:
        document.status = DocumentStatus.DISCOVERED
    document.ingestion_error = None
    document.document_metadata = {
        **(document.document_metadata or {}),
        "relative_path": request.relative_path,
        "filename": request.filename,
        "extension": _extension(request.filename),
        "size": request.size,
        "modified_time": request.modified_time,
        "created_time": request.created_time,
        "parent_directory": request.parent_directory,
        "platform_file_id": request.platform_file_id,
        "source_id": str(source.id),
        "identity_strategy": "platform_file_id" if request.platform_file_id else "relative_path",
        "content_indexed": not request.metadata_only,
        "metadata_only": request.metadata_only,
        "indexing_status": "uploading",
    }
    session.add(document)
    await session.commit()
    await session.refresh(document)

    provider = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    job = await ingest_document_content(
        session=session,
        settings=settings,
        embedding_provider=provider,
        document_id=document.id,
        filename=request.filename,
        content=content,
        mime_type=request.mime_type,
    )
    await session.refresh(document)
    if request.metadata_only and document.status == DocumentStatus.INDEXED:
        document.document_metadata = {
            **(document.document_metadata or {}),
            "content_indexed": False,
            "metadata_only": True,
            "indexing_status": "metadata_only",
        }
        await session.commit()
        await session.refresh(document)
    await _update_source_counts(session, source)
    return LocalFileIngestResponse(
        document_id=document.id,
        status=document.status,
        indexing_status=str(job.status),
        skipped=str(job.status) == "skipped",
        content_hash=request.content_hash,
    )


@router.post("/{source_id}/delete", response_model=LocalDeleteResponse)
async def mark_local_file_deleted(
    source_id: uuid.UUID,
    request: LocalDeleteRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> LocalDeleteResponse:
    require_matching_user(authenticated, request.user_id)
    if source_id != request.source_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source_id mismatch")
    source = await _get_source(session, request.user_id, source_id)
    documents = await _documents_for_delete(session, source, request)
    if not documents:
        return LocalDeleteResponse(document_id=None, status="not_found")
    for document in documents:
        await _mark_document_deleted(session, document)
    await session.commit()
    await _update_source_counts(session, source)
    return LocalDeleteResponse(document_id=documents[0].id, status="deleted")


@router.patch("/{source_id}/status", response_model=LocalSourceResponse)
async def update_local_source_status(
    source_id: uuid.UUID,
    request: LocalSourceStatsRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> LocalSourceResponse:
    require_matching_user(authenticated, request.user_id)
    if source_id != request.source_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "source_id mismatch")
    source = await _get_source(session, request.user_id, source_id)
    metadata = dict(source.source_metadata or {})
    for key in (
        "scan_status",
        "watcher_status",
        "last_detected_event",
        "last_synchronization_error",
        "last_successful_scan",
    ):
        value = getattr(request, key)
        if value is not None:
            metadata[key] = value
    source.source_metadata = metadata
    await session.commit()
    await session.refresh(source)
    return await _source_response(session, source)


def _local_external_id(relative_path: str, platform_file_id: str | None) -> str:
    if platform_file_id:
        return f"platform:{platform_file_id}"
    return f"path:{relative_path}"


async def _documents_for_delete(
    session: AsyncSession,
    source: Source,
    request: LocalDeleteRequest,
) -> list[Document]:
    filters = [
        Document.user_id == request.user_id,
        Document.source_id == source.id,
    ]
    if request.recursive:
        prefix = request.relative_path.rstrip("/") + "/"
        result = await session.execute(
            select(Document).where(
                *filters,
                or_(
                    Document.document_metadata["relative_path"].astext == request.relative_path,
                    Document.document_metadata["relative_path"].astext.like(f"{prefix}%"),
                ),
            )
        )
        return list(result.scalars())
    external_id = _local_external_id(request.relative_path, request.platform_file_id)
    delete_clauses = [
        Document.external_id == external_id,
        Document.external_id == request.relative_path,
        Document.document_metadata["relative_path"].astext == request.relative_path,
    ]
    if request.platform_file_id:
        delete_clauses.append(
            Document.document_metadata["platform_file_id"].astext == request.platform_file_id
        )
    result = await session.execute(select(Document).where(*filters, or_(*delete_clauses)))
    return list(result.scalars())


async def _mark_document_deleted(session: AsyncSession, document: Document) -> None:
    document.status = DocumentStatus.DELETED
    document.searchable_text = None
    document.embedding = None
    document.document_metadata = {
        **(document.document_metadata or {}),
        "indexing_status": "deleted",
        "deleted_at": datetime.now(UTC).isoformat(),
    }
    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    await session.execute(
        delete(DocumentRelationship).where(
            or_(
                DocumentRelationship.source_document_id == document.id,
                DocumentRelationship.target_document_id == document.id,
            )
        )
    )


async def _get_source(session: AsyncSession, user_id: uuid.UUID, source_id: uuid.UUID) -> Source:
    source = (
        await session.execute(
            select(Source).where(
                Source.id == source_id,
                Source.user_id == user_id,
                Source.kind == SourceKind.LOCAL_FOLDER,
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "local source not found")
    return source


async def _source_response(session: AsyncSession, source: Source) -> LocalSourceResponse:
    metadata = dict(source.source_metadata or {})
    indexed = (
        await session.execute(
            select(func.count(Document.id)).where(
                Document.source_id == source.id,
                Document.user_id == source.user_id,
                Document.status == DocumentStatus.INDEXED,
            )
        )
    ).scalar_one()
    failed = (
        await session.execute(
            select(func.count(Document.id)).where(
                Document.source_id == source.id,
                Document.user_id == source.user_id,
                Document.status == DocumentStatus.FAILED,
            )
        )
    ).scalar_one()
    active = (
        await session.execute(
            select(func.count(Document.id)).where(
                Document.source_id == source.id,
                Document.user_id == source.user_id,
                Document.status != DocumentStatus.DELETED,
            )
        )
    ).scalar_one()
    return LocalSourceResponse(
        id=source.id,
        user_id=source.user_id,
        kind=source.kind,
        status=source.status,
        display_name=source.display_name,
        platform=_string(metadata.get("platform")),
        scan_status=_string(metadata.get("scan_status")) or "idle",
        watcher_status=_string(metadata.get("watcher_status")) or "stopped",
        last_successful_scan=_string(metadata.get("last_successful_scan")),
        last_detected_event=_string(metadata.get("last_detected_event")),
        last_synchronization_error=_string(metadata.get("last_synchronization_error")),
        file_count=_int_value(metadata.get("file_count"), int(active or 0)),
        indexed_count=int(indexed or 0),
        failed_count=int(failed or 0),
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


async def _update_source_counts(session: AsyncSession, source: Source) -> None:
    response = await _source_response(session, source)
    source.source_metadata = {
        **(source.source_metadata or {}),
        "file_count": response.file_count,
        "indexed_count": response.indexed_count,
        "failed_count": response.failed_count,
        "last_successful_scan": datetime.now(UTC).isoformat(),
    }
    await session.commit()


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_value(value: object, fallback: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return fallback


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()
