import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import search as search_api
from app.api.search import SearchRequest, search
from app.auth import AuthenticatedUser
from app.core.settings import Settings
from app.ingestion.embeddings import EmbeddingProviderError
from app.main import create_app
from app.search.service import SearchResult, _excerpt, _row_to_result, text_search


class FailingEmbeddingProvider:
    async def embed_texts(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        raise EmbeddingProviderError("provider unavailable")


class FakeExecuteResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class RecordingSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statement = ""
        self.params: dict[str, object] = {}

    async def execute(self, statement: object, params: dict[str, object]) -> FakeExecuteResult:
        self.statement = str(statement)
        self.params = params
        return FakeExecuteResult(self.rows)


@pytest.mark.asyncio
async def test_search_endpoint_falls_back_to_text_search_when_embeddings_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()

    async def fake_text_search(**kwargs: object) -> tuple[SearchResult, ...]:
        return (
            SearchResult(
                document_id=uuid.uuid4(),
                title="fallback.txt",
                type="text/plain",
                score=0.42,
                matching_excerpts=(),
                source_metadata={
                    "kind": "local_folder",
                    "display_name": "Fixture",
                    "metadata": {},
                    "document_metadata": {"indexing_status": "indexed"},
                },
                explanation={
                    "semantic_score": 0.0,
                    "text_score": 0.42,
                    "weights": {"semantic": 0.0, "text": 1.0},
                    "signals": ["chunk_text_match"],
                },
            ),
        )

    monkeypatch.setattr(search_api, "text_search", fake_text_search)
    monkeypatch.setattr(
        search_api,
        "get_embedding_provider",
        lambda settings: FailingEmbeddingProvider(),
    )
    response = await search(
        request=SearchRequest(user_id=user_id, query="memory", limit=5),
        session=object(),  # type: ignore[arg-type]
        authenticated=AuthenticatedUser(id=user_id, email="user@example.com"),
        settings=Settings(GEMINI_API_KEY="test"),
    )

    assert response.results[0]["title"] == "fallback.txt"
    assert response.results[0]["explanation"] == {
        "semantic_score": 0.0,
        "text_score": 0.42,
        "weights": {"semantic": 0.0, "text": 1.0},
        "signals": ["chunk_text_match"],
    }


def test_search_route_falls_back_when_provider_configuration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user_id = uuid.uuid4()

    async def fake_get_session() -> object:
        return object()

    async def fake_current_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=user_id, email="user@example.com")

    async def fake_text_search(**kwargs: object) -> tuple[SearchResult, ...]:
        return (
            SearchResult(
                document_id=uuid.uuid4(),
                title="fallback.txt",
                type="text/plain",
                score=0.31,
                matching_excerpts=(),
                source_metadata={
                    "kind": "local_folder",
                    "display_name": "Fixture",
                    "metadata": {},
                    "document_metadata": {"indexing_status": "indexed"},
                },
                explanation={
                    "semantic_score": 0.0,
                    "text_score": 0.31,
                    "weights": {"semantic": 0.0, "text": 1.0},
                    "signals": ["chunk_text_match"],
                },
            ),
        )

    monkeypatch.setattr(search_api, "text_search", fake_text_search)
    app = create_app()
    app.dependency_overrides[search_api.get_session] = fake_get_session
    app.dependency_overrides[search_api.get_current_user] = fake_current_user
    app.dependency_overrides[search_api.get_settings] = lambda: Settings(GEMINI_API_KEY=None)

    with caplog.at_level("WARNING", logger="app.api.search"):
        with TestClient(app) as client:
            response = client.post("/search", json={"user_id": str(user_id), "query": "memory"})

    assert response.status_code == 200
    assert response.json()["results"][0]["matching_excerpts"] == []
    assert "using text search fallback" in caplog.text
    assert "memory" not in caplog.text
    assert str(user_id) not in caplog.text


@pytest.mark.asyncio
async def test_text_search_scopes_sources_and_does_not_return_chunk_text() -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    session = RecordingSession(
        [
            {
                "document_id": document_id,
                "title": "roadmap.md",
                "mime_type": "text/markdown",
                "status": "indexed",
                "document_metadata": {"source_filename": "roadmap.md"},
                "source_kind": "local_folder",
                "source_display_name": "Fixtures",
                "source_metadata": {},
                "text_rank": 0.63,
                "matching_chunk_count": 2,
            }
        ]
    )

    results = await text_search(
        session=session,  # type: ignore[arg-type]
        user_id=user_id,
        query="semantic roadmap",
        limit=3,
    )

    assert "JOIN sources s ON s.id = d.source_id AND s.user_id = :user_id" in session.statement
    assert "AS excerpts" not in session.statement
    assert "array_agg" not in session.statement
    assert session.params == {
        "query": "semantic roadmap",
        "user_id": user_id,
        "limit": 3,
    }
    assert results[0].document_id == document_id
    assert results[0].score == 0.63
    assert results[0].matching_excerpts == ()


def test_search_result_contains_machine_readable_explanation() -> None:
    result = _row_to_result(
        {
            "document_id": uuid.uuid4(),
            "title": "roadmap.md",
            "mime_type": "text/markdown",
            "status": "indexed",
            "document_metadata": {"source_filename": "roadmap.md"},
            "source_kind": "local_folder",
            "source_display_name": "Fixtures",
            "source_metadata": {},
            "cosine_distance": 0.2,
            "text_rank": 0.5,
            "excerpts": ["The onboarding roadmap mentions semantic search."],
        },
        "semantic search",
    )

    assert result.title == "roadmap.md"
    assert result.score == 0.746
    assert result.explanation["signals"] == [
        "chunk_embedding_cosine_similarity",
        "chunk_text_match",
    ]


def test_drive_search_result_exposes_open_url_metadata() -> None:
    result = _row_to_result(
        {
            "document_id": uuid.uuid4(),
            "title": "Strategy Doc",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "status": "indexed",
            "document_metadata": {
                "google_drive_file_id": "drive-file-1",
                "drive_web_url": "https://drive.google.com/file/d/drive-file-1/view",
                "drive_mime_type": "application/vnd.google-apps.document",
                "modified_time": "2026-07-26T12:00:00Z",
            },
            "source_kind": "google_drive",
            "source_display_name": "user@example.com",
            "source_metadata": {},
            "cosine_distance": 0.1,
            "text_rank": 0.0,
            "excerpts": ["Strategy notes about Memory."],
        },
        "strategy",
    )

    assert result.source_metadata["drive"] == {
        "file_id": "drive-file-1",
        "web_url": "https://drive.google.com/file/d/drive-file-1/view",
        "mime_type": "application/vnd.google-apps.document",
        "modified_time": "2026-07-26T12:00:00Z",
    }
    document_metadata = result.source_metadata["document_metadata"]
    assert isinstance(document_metadata, dict)
    assert document_metadata["indexing_status"] == "indexed"


def test_excerpt_prefers_query_terms() -> None:
    text = "alpha " * 80 + "semantic search lives here " + "omega " * 80

    assert "semantic search" in _excerpt(text, "semantic search")
