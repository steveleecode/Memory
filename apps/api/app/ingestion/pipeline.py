import math
import uuid
from pathlib import Path
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.ingestion.chunking import chunk_document
from app.ingestion.embeddings import EmbeddingProvider
from app.ingestion.extractors import UnsupportedFileTypeError, extract_document
from app.ingestion.hashing import sha256_bytes
from app.ingestion.models import Chunk
from app.ingestion.normalize import normalize_document
from app.models.document import (
    Document,
    DocumentChunk,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
)


class IngestionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def ingest_document_content(
    *,
    session: AsyncSession,
    settings: Settings,
    embedding_provider: EmbeddingProvider,
    document_id: uuid.UUID,
    filename: str,
    content: bytes,
    mime_type: str | None,
) -> IngestionJob:
    document = await session.get(Document, document_id)
    if document is None:
        raise IngestionError("document_not_found", f"Document not found: {document_id}")

    content_hash = sha256_bytes(content)
    job = IngestionJob(
        user_id=document.user_id,
        document_id=document.id,
        content_hash=content_hash,
        status=IngestionJobStatus.RUNNING,
        attempts=1,
    )
    session.add(job)

    if document.indexed_content_hash == content_hash and document.status == DocumentStatus.INDEXED:
        job.status = IngestionJobStatus.SKIPPED
        await session.commit()
        await session.refresh(job)
        return job

    try:
        document.status = DocumentStatus.EXTRACTING
        document.ingestion_error = None
        await session.flush()

        extracted = normalize_document(extract_document(Path(filename), content, mime_type))
        chunks = chunk_document(
            extracted,
            model=settings.embedding_model,
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
        if not chunks:
            raise IngestionError(
                "empty_extraction",
                "No indexable text was extracted from the file",
            )

        representation = build_document_representation(
            filename=filename,
            title=document.title,
            metadata=document.document_metadata,
            chunks=chunks,
        )
        embeddings = await embedding_provider.embed_texts(
            [chunk.text for chunk in chunks] + [representation],
        )
        chunk_embeddings = embeddings[:-1]
        document_embedding = embeddings[-1]

        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        for chunk, embedding in zip(chunks, chunk_embeddings, strict=True):
            session.add(
                DocumentChunk(
                    user_id=document.user_id,
                    document_id=document.id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    content_hash=chunk.content_hash,
                    embedding=embedding,
                    chunk_metadata=chunk.metadata,
                )
            )

        document.content_hash = content_hash
        document.indexed_content_hash = content_hash
        document.mime_type = mime_type or document.mime_type
        document.searchable_text = representation
        document.embedding = _normalize(document_embedding)
        document.document_metadata = {
            **document.document_metadata,
            "extraction": extracted.metadata,
            "source_filename": filename,
            "chunk_count": len(chunks),
        }
        document.status = DocumentStatus.INDEXED
        job.status = IngestionJobStatus.SUCCEEDED
    except UnsupportedFileTypeError as exc:
        _mark_failed(document, job, "unsupported_file_type", str(exc))
    except IngestionError as exc:
        _mark_failed(document, job, exc.code, str(exc))
    except Exception as exc:
        _mark_failed(document, job, "ingestion_failed", str(exc))

    await session.commit()
    await session.refresh(job)
    return job


async def get_document_for_user(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document | None:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    return result.scalar_one_or_none()


def build_document_representation(
    *,
    filename: str,
    title: str,
    metadata: dict[str, object],
    chunks: tuple[Chunk, ...],
) -> str:
    heading_parts: list[str] = []
    for chunk in chunks:
        heading_parts.extend(_metadata_strings(chunk.metadata.get("headings", [])))
        heading_parts.extend(_metadata_strings(chunk.metadata.get("sections", [])))
    headings = "\n".join(dict.fromkeys(heading_parts))
    extracted = "\n\n".join(chunk.text for chunk in chunks)
    metadata_text = "\n".join(f"{key}: {value}" for key, value in sorted(metadata.items()))
    return "\n\n".join(
        part
        for part in [
            f"Filename: {filename}",
            f"Title: {title}",
            metadata_text,
            headings,
            extracted,
        ]
        if part.strip()
    )


def _metadata_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value) if item]


def _normalize(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


def _mark_failed(
    document: Document,
    job: IngestionJob,
    code: str,
    message: str,
) -> None:
    document.status = DocumentStatus.FAILED
    document.ingestion_error = message
    job.status = IngestionJobStatus.FAILED
    job.failure_code = code
    job.failure_message = message
