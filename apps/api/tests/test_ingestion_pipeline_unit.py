import uuid
from typing import Any

import pytest

from app.core.settings import Settings
from app.ingestion.embeddings import DeterministicTestEmbeddingProvider
from app.ingestion.hashing import sha256_bytes
from app.ingestion.models import Chunk
from app.ingestion.pipeline import build_search_representation_specs, ingest_document_content
from app.models.document import (
    Document,
    DocumentStatus,
    IngestionJobStatus,
    SearchRepresentation,
    SearchRepresentationType,
)


class FakeSession:
    def __init__(self, document: Document) -> None:
        self.document = document
        self.added: list[Any] = []
        self.executed: list[Any] = []
        self.committed = False

    async def get(self, model: type[Document], document_id: uuid.UUID) -> Document | None:
        assert model is Document
        assert document_id == self.document.id
        return self.document

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)

    async def flush(self) -> None:
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid.uuid4()

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, item: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_ingestion_skips_unchanged_indexed_content() -> None:
    content = b"alpha search notes about private memory"
    document = Document(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        external_id="alpha.txt",
        title="alpha.txt",
        status=DocumentStatus.INDEXED,
        content_hash=sha256_bytes(content),
        indexed_content_hash=sha256_bytes(content),
        document_metadata={},
    )
    session = FakeSession(document)

    job = await ingest_document_content(
        session=session,  # type: ignore[arg-type]
        settings=Settings(GEMINI_API_KEY="test"),
        embedding_provider=DeterministicTestEmbeddingProvider(),
        document_id=document.id,
        filename="alpha.txt",
        content=content,
        mime_type="text/plain",
    )

    assert job.status == IngestionJobStatus.SKIPPED
    assert session.committed is True


def test_image_without_ocr_or_caption_only_builds_filename_representation() -> None:
    specs = build_search_representation_specs(
        filename="cornell-project-screenshot.png",
        title="cornell-project-screenshot.png",
        mime_type="image/png",
        metadata={},
        chunks=(),
        embedding_model="test-embedding",
    )

    assert [spec.representation_type for spec in specs] == [SearchRepresentationType.FILENAME]
    assert specs[0].source_content == "cornell-project-screenshot.png"


def test_high_confidence_ocr_uses_ocr_representation() -> None:
    specs = build_search_representation_specs(
        filename="scan.png",
        title="scan.png",
        mime_type="image/png",
        metadata={},
        chunks=(
            Chunk(
                ordinal=0,
                text="Cornell project approval",
                token_count=3,
                content_hash="hash",
                metadata={"extraction_source": "ocr", "ocr_confidence": 0.94},
            ),
        ),
        embedding_model="test-embedding",
    )

    assert specs[0].representation_type == SearchRepresentationType.OCR_TEXT
    assert specs[0].source_confidence == 0.94


@pytest.mark.asyncio
async def test_image_ingestion_records_filename_provenance_without_document_text() -> None:
    document = Document(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        external_id="image.png",
        title="image.png",
        status=DocumentStatus.DISCOVERED,
        document_metadata={},
    )
    session = FakeSession(document)

    job = await ingest_document_content(
        session=session,  # type: ignore[arg-type]
        settings=Settings(GEMINI_API_KEY="test"),
        embedding_provider=DeterministicTestEmbeddingProvider(),
        document_id=document.id,
        filename="image.png",
        content=b"\x89PNG\r\n",
        mime_type="image/png",
    )

    representations = [item for item in session.added if isinstance(item, SearchRepresentation)]
    assert job.status == IngestionJobStatus.SUCCEEDED
    assert document.document_metadata["has_extracted_text"] is False
    assert [item.representation_type for item in representations] == [
        SearchRepresentationType.FILENAME
    ]
