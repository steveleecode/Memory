import argparse
import asyncio
import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import AsyncSessionLocal
from app.ingestion.embeddings import GeminiEmbeddingProvider
from app.ingestion.pipeline import ingest_document_content
from app.models.document import Document, DocumentStatus
from app.models.source import Source, SourceKind, SourceStatus
from app.models.user import User
from app.search.service import semantic_search


def main() -> None:
    parser = argparse.ArgumentParser(prog="memory-api")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser(
        "ingest-fixtures", help="Ingest a directory of local fixture files"
    )
    ingest.add_argument("directory", type=Path)
    ingest.add_argument("--user-email", default="developer@memory.local")
    ingest.add_argument("--source-name", default="Fixture Directory")

    search = subparsers.add_parser("search", help="Run semantic search for a user")
    search.add_argument("query")
    search.add_argument("--user-email", default="developer@memory.local")
    search.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()
    if args.command == "ingest-fixtures":
        asyncio.run(_ingest_fixtures(args.directory, args.user_email, args.source_name))
    elif args.command == "search":
        asyncio.run(_search(args.query, args.user_email, args.limit))


async def _ingest_fixtures(directory: Path, user_email: str, source_name: str) -> None:
    settings = get_settings()
    provider = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    if not files:
        raise SystemExit(f"No files found in {directory}")

    async with AsyncSessionLocal() as session:
        user = await _get_or_create_user(session, user_email)
        source = await _get_or_create_fixture_source(session, user.id, source_name, directory)

        results: list[dict[str, Any]] = []
        for path in files:
            relative = path.relative_to(directory)
            mime_type = mimetypes.guess_type(path.name)[0]
            document = await _get_or_create_document(
                session=session,
                user_id=user.id,
                source_id=source.id,
                external_id=str(relative),
                title=path.name,
                mime_type=mime_type,
            )
            job = await ingest_document_content(
                session=session,
                settings=settings,
                embedding_provider=provider,
                document_id=document.id,
                filename=path.name,
                content=path.read_bytes(),
                mime_type=mime_type,
            )
            results.append(
                {
                    "file": str(relative),
                    "document_id": str(document.id),
                    "job_id": str(job.id),
                    "status": job.status.value,
                    "failure_code": job.failure_code,
                    "failure_message": job.failure_message,
                }
            )

    print(json.dumps({"ingested": results}, indent=2))


async def _search(query: str, user_email: str, limit: int) -> None:
    settings = get_settings()
    provider = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == user_email))
        user = result.scalar_one_or_none()
        if user is None:
            raise SystemExit(f"No user found for email {user_email}. Ingest fixtures first.")
        results = await semantic_search(
            session=session,
            embedding_provider=provider,
            user_id=user.id,
            query=query,
            limit=limit,
        )
    print(
        json.dumps(
            {
                "query": query,
                "results": [
                    {
                        "document_id": str(item.document_id),
                        "title": item.title,
                        "type": item.type,
                        "score": item.score,
                        "matching_excerpts": item.matching_excerpts,
                        "source_metadata": item.source_metadata,
                        "explanation": item.explanation,
                    }
                    for item in results
                ],
            },
            indent=2,
        )
    )


async def _get_or_create_user(session: AsyncSession, email: str) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(email=email, display_name="Memory Developer")
    session.add(user)
    await session.flush()
    return user


async def _get_or_create_fixture_source(
    session: AsyncSession,
    user_id: uuid.UUID,
    source_name: str,
    directory: Path,
) -> Source:
    external_id = str(directory.resolve())
    result = await session.execute(
        select(Source).where(
            Source.user_id == user_id,
            Source.kind == SourceKind.LOCAL_FOLDER,
            Source.external_id == external_id,
        )
    )
    source = result.scalar_one_or_none()
    if source is not None:
        return source
    source = Source(
        user_id=user_id,
        kind=SourceKind.LOCAL_FOLDER,
        status=SourceStatus.ACTIVE,
        external_id=external_id,
        display_name=source_name,
        source_metadata={"fixture_directory": external_id},
    )
    session.add(source)
    await session.flush()
    return source


async def _get_or_create_document(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    external_id: str,
    title: str,
    mime_type: str | None,
) -> Document:
    result = await session.execute(
        select(Document).where(Document.source_id == source_id, Document.external_id == external_id)
    )
    document = result.scalar_one_or_none()
    if document is not None:
        return document
    document = Document(
        user_id=user_id,
        source_id=source_id,
        external_id=external_id,
        title=title,
        mime_type=mime_type,
        status=DocumentStatus.DISCOVERED,
        document_metadata={"source_filename": title},
    )
    session.add(document)
    await session.flush()
    return document


if __name__ == "__main__":
    main()
