import math
import uuid
from dataclasses import dataclass
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
    SearchRepresentation,
    SearchRepresentationType,
)

EXTRACTOR_VERSION = "memory.extractors.v1"


class IngestionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SearchRepresentationSpec:
    representation_type: SearchRepresentationType
    source_content: str
    source_confidence: float | None = None
    chunk_ordinal: int | None = None
    metadata: dict[str, object] | None = None


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

        chunks: tuple[Chunk, ...] = ()
        extracted_metadata: dict[str, object] = {}
        has_extracted_text = False
        is_image = (mime_type or "").startswith("image/")
        if not is_image:
            extracted = normalize_document(extract_document(Path(filename), content, mime_type))
            extracted_metadata = extracted.metadata
            chunks = chunk_document(
                extracted,
                model=settings.embedding_model,
                target_tokens=settings.chunk_target_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
            has_extracted_text = bool(extracted.text.strip())
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
        specs = build_search_representation_specs(
            filename=filename,
            title=document.title,
            mime_type=mime_type,
            metadata=document.document_metadata,
            chunks=chunks,
            embedding_model=settings.embedding_model,
        )
        if not specs:
            raise IngestionError("empty_representations", "No indexable search representations")

        embeddings = await embedding_provider.embed_texts(
            [chunk.text for chunk in chunks]
            + [representation]
            + [spec.source_content for spec in specs],
        )
        chunk_embeddings = embeddings[: len(chunks)]
        document_embedding = embeddings[len(chunks)]
        representation_embeddings = embeddings[len(chunks) + 1 :]

        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        await session.execute(
            delete(SearchRepresentation).where(SearchRepresentation.document_id == document.id)
        )
        chunk_ids: dict[int, uuid.UUID] = {}
        for chunk, embedding in zip(chunks, chunk_embeddings, strict=True):
            document_chunk = DocumentChunk(
                user_id=document.user_id,
                document_id=document.id,
                ordinal=chunk.ordinal,
                text=chunk.text,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                embedding=embedding,
                chunk_metadata=chunk.metadata,
            )
            session.add(document_chunk)
            await session.flush()
            chunk_ids[chunk.ordinal] = document_chunk.id

        for spec, embedding in zip(specs, representation_embeddings, strict=True):
            chunk_id = chunk_ids.get(spec.chunk_ordinal) if spec.chunk_ordinal is not None else None
            session.add(
                SearchRepresentation(
                    user_id=document.user_id,
                    document_id=document.id,
                    chunk_id=chunk_id,
                    representation_type=spec.representation_type,
                    mime_type=mime_type,
                    source_content=spec.source_content,
                    source_confidence=spec.source_confidence,
                    embedding_model=settings.embedding_model,
                    embedding_model_version=settings.embedding_model,
                    extractor_version=EXTRACTOR_VERSION,
                    content_hash=sha256_bytes(spec.source_content.encode("utf-8")),
                    embedding=_normalize(embedding),
                    representation_metadata=spec.metadata or {},
                )
            )

        document.content_hash = content_hash
        document.indexed_content_hash = content_hash
        document.mime_type = mime_type or document.mime_type
        document.searchable_text = representation
        document.embedding = _normalize(document_embedding)
        document.document_metadata = {
            **document.document_metadata,
            "extraction": extracted_metadata,
            "source_filename": filename,
            "chunk_count": len(chunks),
            "has_extracted_text": has_extracted_text,
            "search_representation_version": 1,
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


def build_search_representation_specs(
    *,
    filename: str,
    title: str,
    mime_type: str | None,
    metadata: dict[str, object],
    chunks: tuple[Chunk, ...],
    embedding_model: str,
) -> tuple[SearchRepresentationSpec, ...]:
    specs: list[SearchRepresentationSpec] = []
    for chunk in chunks:
        specs.append(
            SearchRepresentationSpec(
                representation_type=_text_representation_type(mime_type, chunk.metadata),
                source_content=chunk.text,
                source_confidence=_confidence(chunk.metadata.get("ocr_confidence")),
                chunk_ordinal=chunk.ordinal,
                metadata={"chunk_metadata": chunk.metadata, "embedding_model": embedding_model},
            )
        )

    _append_source_signal(specs, SearchRepresentationType.FILENAME, filename, metadata={})
    relative_path = metadata.get("relative_path")
    if isinstance(relative_path, str) and relative_path and relative_path != filename:
        _append_source_signal(specs, SearchRepresentationType.FILE_PATH, relative_path, metadata={})

    useful_metadata = {
        key: value
        for key, value in metadata.items()
        if key
        in {
            "description",
            "drive_mime_type",
            "extension",
            "kind",
            "labels",
            "tags",
        }
        and value
    }
    if title and title != filename:
        useful_metadata["title"] = title
    if useful_metadata:
        _append_source_signal(
            specs,
            SearchRepresentationType.METADATA,
            "\n".join(f"{key}: {value}" for key, value in sorted(useful_metadata.items())),
            metadata={"metadata_keys": sorted(useful_metadata)},
        )

    caption = metadata.get("image_caption")
    if isinstance(caption, str):
        _append_source_signal(
            specs,
            SearchRepresentationType.IMAGE_CAPTION,
            caption,
            source_confidence=_confidence(metadata.get("image_caption_confidence")),
            metadata={"captioner_version": metadata.get("captioner_version", "unknown")},
        )
    return tuple(specs)


def _text_representation_type(
    mime_type: str | None,
    metadata: dict[str, object],
) -> SearchRepresentationType:
    if (mime_type or "").startswith("image/") or metadata.get("extraction_source") == "ocr":
        return SearchRepresentationType.OCR_TEXT
    return SearchRepresentationType.DOCUMENT_TEXT


def _append_source_signal(
    specs: list[SearchRepresentationSpec],
    representation_type: SearchRepresentationType,
    source_content: str,
    *,
    source_confidence: float | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    cleaned = source_content.strip()
    if not _is_indexable_signal(cleaned):
        return
    specs.append(
        SearchRepresentationSpec(
            representation_type=representation_type,
            source_content=cleaned,
            source_confidence=source_confidence,
            metadata=metadata or {},
        )
    )


def _is_indexable_signal(value: str) -> bool:
    lowered = value.lower().strip()
    return bool(lowered) and lowered not in {"untitled", "unknown", "n/a", "none", "placeholder"}


def _confidence(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


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
