import uuid
from typing import Any

import pytest

from app.core.settings import Settings
from app.ingestion.embeddings import DeterministicTestEmbeddingProvider
from app.ingestion.hashing import sha256_bytes
from app.ingestion.pipeline import ingest_document_content
from app.models.document import Document, DocumentStatus, IngestionJobStatus


class FakeSession:
    def __init__(self, document: Document) -> None:
        self.document = document
        self.added: list[Any] = []
        self.committed = False

    async def get(self, model: type[Document], document_id: uuid.UUID) -> Document | None:
        assert model is Document
        assert document_id == self.document.id
        return self.document

    def add(self, item: Any) -> None:
        self.added.append(item)

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
