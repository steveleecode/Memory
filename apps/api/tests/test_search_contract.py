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
from app.search.service import (
    SearchResult,
    _excerpt,
    _row_to_result,
    _search_params,
    semantic_search,
    text_search,
)


class FailingEmbeddingProvider:
    async def embed_texts(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        raise EmbeddingProviderError("provider unavailable")


class StaticEmbeddingProvider:
    async def embed_texts(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [(0.1, 0.2, 0.3) for _ in texts]


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


def explanation_fixture(
    score: float,
    representation_type: str = "document_text",
) -> dict[str, object]:
    return {
        "final_score": score,
        "semantic_score": 0.0,
        "text_score": score,
        "matched_representation_type": representation_type,
        "has_extracted_text": representation_type == "document_text",
        "signals": [
            {
                "type": representation_type,
                "score": score,
                "raw_text_score": score,
                "matched_content": "fallback.txt",
                "applied_weight": 1.0,
            }
        ],
    }


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
                explanation=explanation_fixture(0.42),
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
    assert response.results[0]["explanation"] == explanation_fixture(0.42)


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
                explanation=explanation_fixture(0.31),
            ),
        )

    monkeypatch.setattr(search_api, "text_search", fake_text_search)
    app = create_app()
    app.dependency_overrides[search_api.get_session] = fake_get_session
    app.dependency_overrides[search_api.get_current_user] = fake_current_user
    app.dependency_overrides[search_api.get_settings] = lambda: Settings(GEMINI_API_KEY=None)

    with caplog.at_level("WARNING", logger="app.api.search"), TestClient(app) as client:
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
                "final_score": 0.63,
                "signal_count": 1,
                "excerpts": [],
                "matched_representation_type": "document_text",
                "signals": [
                    {
                        "type": "document_text",
                        "score": 0.63,
                        "raw_semantic_score": 0.0,
                        "raw_text_score": 0.63,
                        "matched_content": "semantic roadmap",
                        "applied_weight": 1.0,
                    }
                ],
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
    assert "FROM search_representations sr" in session.statement
    assert "FROM document_chunks dc" not in session.statement
    assert "CAST(:weight_document_text AS double precision)" in session.statement
    assert "CAST(:strong_filename_text_rank AS double precision)" in session.statement
    assert "CAST(:min_ocr_confidence AS double precision)" in session.statement
    assert "d.mime_type NOT LIKE 'image/%'" in session.statement
    assert session.params["include_images"] is False
    assert session.params["query"] == "semantic roadmap"
    assert session.params["user_id"] == user_id
    assert session.params["limit"] == 3
    assert results[0].document_id == document_id
    assert results[0].score == 0.63
    assert results[0].matching_excerpts == ()
    assert results[0].explanation["matched_representation_type"] == "document_text"


@pytest.mark.asyncio
async def test_semantic_search_casts_weight_parameters_for_asyncpg() -> None:
    user_id = uuid.uuid4()
    session = RecordingSession(
        [
            {
                "document_id": uuid.uuid4(),
                "title": "roadmap.md",
                "mime_type": "text/markdown",
                "status": "indexed",
                "document_metadata": {"source_filename": "roadmap.md"},
                "source_kind": "local_folder",
                "source_display_name": "Fixtures",
                "source_metadata": {},
                "final_score": 0.72,
                "signal_count": 1,
                "excerpts": ["semantic roadmap"],
                "matched_representation_type": "document_text",
                "signals": [
                    {
                        "type": "document_text",
                        "score": 0.72,
                        "raw_semantic_score": 0.8,
                        "raw_text_score": 0.3,
                        "matched_content": "semantic roadmap",
                    }
                ],
            }
        ]
    )

    results = await semantic_search(
        session=session,  # type: ignore[arg-type]
        embedding_provider=StaticEmbeddingProvider(),
        user_id=user_id,
        query="semantic roadmap",
        limit=3,
    )

    assert results[0].score == 0.72
    assert "CAST(:weight_document_text AS double precision)" in session.statement
    assert "CAST(:weight_filename AS double precision)" in session.statement
    assert "CAST(:semantic_weight AS double precision)" in session.statement
    assert "CAST(:text_weight AS double precision)" in session.statement
    assert "CAST(:min_image_single_signal_score AS double precision)" in session.statement
    assert "d.mime_type NOT LIKE 'image/%'" in session.statement
    assert session.params["include_images"] is False


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
            "final_score": 0.746,
            "signal_count": 1,
            "excerpts": ["The onboarding roadmap mentions semantic search."],
            "matched_representation_type": "document_text",
            "signals": [
                {
                    "type": "document_text",
                    "score": 0.746,
                    "raw_semantic_score": 0.8,
                    "raw_text_score": 0.5,
                    "matched_content": "The onboarding roadmap mentions semantic search.",
                    "source_confidence": None,
                    "applied_weight": 1.0,
                }
            ],
        },
        "semantic search",
    )

    assert result.title == "roadmap.md"
    assert result.score == 0.746
    assert result.explanation["matched_representation_type"] == "document_text"
    assert result.explanation["signals"] == [
        {
            "type": "document_text",
            "score": 0.746,
            "raw_semantic_score": 0.8,
            "raw_text_score": 0.5,
            "matched_content": "The onboarding roadmap mentions semantic search.",
            "source_confidence": None,
            "applied_weight": 1.0,
        }
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
            "final_score": 0.738,
            "signal_count": 1,
            "excerpts": ["Strategy notes about Memory."],
            "matched_representation_type": "document_text",
            "signals": [
                {
                    "type": "document_text",
                    "score": 0.738,
                    "raw_semantic_score": 0.9,
                    "raw_text_score": 0.0,
                    "matched_content": "Strategy notes about Memory.",
                }
            ],
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


def test_image_filename_match_is_not_reported_as_document_text() -> None:
    result = _row_to_result(
        search_row(
            mime_type="image/png",
            metadata={"has_extracted_text": False},
            signals=[
                {
                    "type": "filename",
                    "score": 0.71,
                    "raw_semantic_score": 0.8,
                    "raw_text_score": 0.2,
                    "matched_content": "cornell-project-screenshot.png",
                }
            ],
        ),
        "cornell project",
    )

    assert result.explanation["matched_representation_type"] == "filename"
    assert result.explanation["has_extracted_text"] is False
    assert result.matching_excerpts == ()


def test_visual_similarity_is_never_labeled_as_text_similarity() -> None:
    result = _row_to_result(
        search_row(
            mime_type="image/png",
            metadata={"has_extracted_text": False},
            signals=[
                {
                    "type": "visual_embedding",
                    "score": 0.49,
                    "raw_semantic_score": 0.9,
                    "raw_text_score": 0.0,
                    "matched_content": "visual-vector",
                }
            ],
        ),
        "dashboard",
    )

    assert result.explanation["matched_representation_type"] == "visual_embedding"
    assert result.explanation["text_score"] == 0.0


def test_multiple_signals_are_preserved_in_rank_order() -> None:
    result = _row_to_result(
        search_row(
            mime_type="image/png",
            metadata={"has_extracted_text": True},
            matched_type="ocr_text",
            signals=[
                {
                    "type": "ocr_text",
                    "score": 0.78,
                    "raw_semantic_score": 0.8,
                    "raw_text_score": 0.6,
                    "matched_content": "Cornell project approval",
                    "source_confidence": 0.93,
                },
                {
                    "type": "filename",
                    "score": 0.52,
                    "raw_semantic_score": 0.7,
                    "raw_text_score": 0.1,
                    "matched_content": "approval.png",
                },
            ],
        ),
        "cornell approval",
    )

    signals = result.explanation["signals"]
    assert isinstance(signals, list)
    assert [signal["type"] for signal in signals] == ["ocr_text", "filename"]
    assert result.matching_excerpts == ("Cornell project approval",)


def test_missing_timestamps_and_metadata_are_safe() -> None:
    result = _row_to_result(
        search_row(metadata={}, signals=[{"type": "metadata", "score": 0.2}]),
        "anything",
    )

    assert result.source_metadata["document_metadata"] == {"indexing_status": "indexed"}
    assert result.explanation["matched_representation_type"] == "metadata"


def test_low_confidence_ocr_and_generic_caption_weights_are_named_configuration() -> None:
    params = _search_params(Settings(GEMINI_API_KEY="test"))

    assert params["low_ocr_weight"] < params["weight_ocr_text"]
    assert params["generic_caption_weight"] < params["weight_image_caption"]
    assert "min_ocr_confidence" in params
    assert "min_image_single_signal_score" in params
    assert "strong_filename_text_rank" in params
    assert params["include_images"] is False


def search_row(
    *,
    mime_type: str = "text/plain",
    metadata: dict[str, object] | None = None,
    signals: list[dict[str, object]],
    matched_type: str | None = None,
) -> dict[str, object]:
    return {
        "document_id": uuid.uuid4(),
        "title": "result",
        "mime_type": mime_type,
        "status": "indexed",
        "document_metadata": metadata or {},
        "source_kind": "local_folder",
        "source_display_name": "Fixtures",
        "source_metadata": {},
        "final_score": signals[0].get("score", 0.0),
        "signal_count": len(signals),
        "excerpts": [signal.get("matched_content", "") for signal in signals],
        "matched_representation_type": matched_type or signals[0].get("type", "metadata"),
        "signals": signals,
    }


def test_excerpt_prefers_query_terms() -> None:
    text = "alpha " * 80 + "semantic search lives here " + "omega " * 80

    assert "semantic search" in _excerpt(text, "semantic search")
