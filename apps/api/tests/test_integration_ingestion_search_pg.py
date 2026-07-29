import os
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.local_sources import _mark_document_deleted
from app.core.settings import Settings
from app.ingestion.embeddings import DeterministicTestEmbeddingProvider
from app.ingestion.pipeline import ingest_document_content
from app.models.document import Document, DocumentChunk
from app.models.source import Source, SourceKind, SourceStatus
from app.models.user import User
from app.search.service import semantic_search, text_search

pytestmark = pytest.mark.skipif(
    not os.getenv("MEMORY_INTEGRATION_DATABASE_URL"),
    reason="Set MEMORY_INTEGRATION_DATABASE_URL to run PostgreSQL/pgvector integration tests",
)


@pytest.mark.asyncio
async def test_ingestion_persists_vectors_and_search_is_user_isolated() -> None:
    engine = create_async_engine(os.environ["MEMORY_INTEGRATION_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(GEMINI_API_KEY="test")
    provider = DeterministicTestEmbeddingProvider()
    marker = uuid.uuid4().hex

    async with sessionmaker() as session:
        user = User(email=f"{marker}@memory.local")
        other_user = User(email=f"{marker}-other@memory.local")
        session.add_all([user, other_user])
        await session.flush()
        source = Source(
            user_id=user.id,
            kind=SourceKind.LOCAL_FOLDER,
            status=SourceStatus.ACTIVE,
            external_id=f"fixture-{marker}",
            display_name="Fixture",
            source_metadata={},
        )
        other_source = Source(
            user_id=other_user.id,
            kind=SourceKind.LOCAL_FOLDER,
            status=SourceStatus.ACTIVE,
            external_id=f"fixture-other-{marker}",
            display_name="Other Fixture",
            source_metadata={},
        )
        session.add_all([source, other_source])
        await session.flush()
        alpha = Document(
            user_id=user.id,
            source_id=source.id,
            external_id="alpha.txt",
            title="alpha.txt",
            document_metadata={},
        )
        private_other = Document(
            user_id=other_user.id,
            source_id=other_source.id,
            external_id="private.txt",
            title="private.txt",
            document_metadata={},
        )
        session.add_all([alpha, private_other])
        await session.commit()

        await ingest_document_content(
            session=session,
            settings=settings,
            embedding_provider=provider,
            document_id=alpha.id,
            filename="alpha.txt",
            content=b"alpha project launch plan semantic search onboarding",
            mime_type="text/plain",
        )
        await ingest_document_content(
            session=session,
            settings=settings,
            embedding_provider=provider,
            document_id=private_other.id,
            filename="private.txt",
            content=b"alpha project launch plan should not cross users",
            mime_type="text/plain",
        )

        chunk_count = (
            await session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == alpha.id)
            )
        ).scalars()
        results = await semantic_search(
            session=session,
            embedding_provider=provider,
            user_id=user.id,
            query="alpha launch semantic search",
            limit=5,
        )

        await session.execute(delete(User).where(User.email.like(f"{marker}%")))
        await session.commit()

    await engine.dispose()

    assert len(list(chunk_count)) >= 1
    assert results
    assert results[0].document_id == alpha.id
    assert all(result.document_id != private_other.id for result in results)


@pytest.mark.asyncio
async def test_local_delete_removes_chunks_from_active_search() -> None:
    engine = create_async_engine(os.environ["MEMORY_INTEGRATION_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(GEMINI_API_KEY="test")
    provider = DeterministicTestEmbeddingProvider()
    marker = uuid.uuid4().hex

    async with sessionmaker() as session:
        user = User(email=f"{marker}@memory.local")
        session.add(user)
        await session.flush()
        source = Source(
            user_id=user.id,
            kind=SourceKind.LOCAL_FOLDER,
            status=SourceStatus.ACTIVE,
            external_id=f"fixture-{marker}",
            display_name="Fixture",
            source_metadata={},
        )
        session.add(source)
        await session.flush()
        document = Document(
            user_id=user.id,
            source_id=source.id,
            external_id="platform:fixture",
            title="delete-me.txt",
            document_metadata={"relative_path": "delete-me.txt"},
        )
        session.add(document)
        await session.commit()

        await ingest_document_content(
            session=session,
            settings=settings,
            embedding_provider=provider,
            document_id=document.id,
            filename="delete-me.txt",
            content=b"delete me semantic memory cleanup",
            mime_type="text/plain",
        )
        await _mark_document_deleted(session, document)
        await session.commit()

        chunks = (
            await session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
        ).scalars()
        results = await semantic_search(
            session=session,
            embedding_provider=provider,
            user_id=user.id,
            query="semantic memory cleanup",
            limit=5,
        )

        await session.execute(delete(User).where(User.email.like(f"{marker}%")))
        await session.commit()

    await engine.dispose()

    assert list(chunks) == []
    assert all(result.document_id != document.id for result in results)


@pytest.mark.asyncio
async def test_text_search_is_user_source_scoped_and_excludes_deleted_documents() -> None:
    engine = create_async_engine(os.environ["MEMORY_INTEGRATION_DATABASE_URL"])
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(GEMINI_API_KEY="test")
    provider = DeterministicTestEmbeddingProvider()
    marker = uuid.uuid4().hex

    async with sessionmaker() as session:
        user = User(email=f"{marker}@memory.local")
        other_user = User(email=f"{marker}-other@memory.local")
        session.add_all([user, other_user])
        await session.flush()
        source = Source(
            user_id=user.id,
            kind=SourceKind.LOCAL_FOLDER,
            status=SourceStatus.ACTIVE,
            external_id=f"fixture-{marker}",
            display_name="Fixture",
            source_metadata={},
        )
        other_source = Source(
            user_id=other_user.id,
            kind=SourceKind.LOCAL_FOLDER,
            status=SourceStatus.ACTIVE,
            external_id=f"fixture-other-{marker}",
            display_name="Other Fixture",
            source_metadata={"private": True},
        )
        session.add_all([source, other_source])
        await session.flush()
        visible = Document(
            user_id=user.id,
            source_id=source.id,
            external_id="visible.txt",
            title="visible.txt",
            document_metadata={},
        )
        mismatched_source = Document(
            user_id=user.id,
            source_id=other_source.id,
            external_id="mismatched.txt",
            title="mismatched.txt",
            document_metadata={},
        )
        deleted = Document(
            user_id=user.id,
            source_id=source.id,
            external_id="deleted.txt",
            title="deleted.txt",
            document_metadata={},
        )
        session.add_all([visible, mismatched_source, deleted])
        await session.commit()

        await ingest_document_content(
            session=session,
            settings=settings,
            embedding_provider=provider,
            document_id=visible.id,
            filename="visible.txt",
            content=b"needle memory fallback searchable content",
            mime_type="text/plain",
        )
        await ingest_document_content(
            session=session,
            settings=settings,
            embedding_provider=provider,
            document_id=mismatched_source.id,
            filename="mismatched.txt",
            content=b"needle memory fallback should not expose mismatched source",
            mime_type="text/plain",
        )
        await ingest_document_content(
            session=session,
            settings=settings,
            embedding_provider=provider,
            document_id=deleted.id,
            filename="deleted.txt",
            content=b"needle memory fallback deleted document",
            mime_type="text/plain",
        )
        await _mark_document_deleted(session, deleted)
        await session.commit()

        results = await text_search(
            session=session,
            user_id=user.id,
            query="needle memory fallback",
            limit=10,
        )

        await session.execute(delete(User).where(User.email.like(f"{marker}%")))
        await session.commit()

    await engine.dispose()

    assert [result.document_id for result in results] == [visible.id]
    assert results[0].matching_excerpts == ()
    assert results[0].source_metadata["display_name"] == "Fixture"
