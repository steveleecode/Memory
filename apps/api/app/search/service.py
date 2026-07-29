import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.embeddings import EmbeddingProvider


@dataclass(frozen=True)
class SearchResult:
    document_id: uuid.UUID
    title: str
    type: str | None
    score: float
    matching_excerpts: tuple[str, ...]
    source_metadata: dict[str, object]
    explanation: dict[str, object]


async def semantic_search(
    *,
    session: AsyncSession,
    embedding_provider: EmbeddingProvider,
    user_id: uuid.UUID,
    query: str,
    limit: int = 10,
) -> tuple[SearchResult, ...]:
    query_embedding = (await embedding_provider.embed_texts([query]))[0]
    vector_literal = "[" + ",".join(str(float(value)) for value in query_embedding) + "]"
    rows = (
        await session.execute(
            text(
                """
                WITH semantic_matches AS (
                    SELECT
                        dc.document_id,
                        MIN(dc.embedding <=> CAST(:query_embedding AS vector)) AS cosine_distance,
                        MAX(
                            ts_rank_cd(
                                to_tsvector('english', dc.text),
                                plainto_tsquery('english', :query)
                            )
                        ) AS text_rank,
                        array_agg(
                            dc.text
                            ORDER BY dc.embedding <=> CAST(:query_embedding AS vector)
                        ) AS excerpts
                    FROM document_chunks dc
                    WHERE dc.user_id = :user_id
                      AND dc.embedding IS NOT NULL
                    GROUP BY dc.document_id
                )
                SELECT
                    d.id AS document_id,
                    d.title,
                    d.mime_type,
                    d.status,
                    d.document_metadata,
                    s.kind AS source_kind,
                    s.display_name AS source_display_name,
                    s.source_metadata,
                    semantic_matches.cosine_distance,
                    semantic_matches.text_rank,
                    semantic_matches.excerpts
                FROM semantic_matches
                JOIN documents d ON d.id = semantic_matches.document_id
                JOIN sources s ON s.id = d.source_id AND s.user_id = :user_id
                WHERE d.user_id = :user_id
                  AND d.status != 'deleted'
                ORDER BY
                    ((1.0 - semantic_matches.cosine_distance) * 0.82)
                    + (LEAST(COALESCE(semantic_matches.text_rank, 0), 1.0) * 0.18) DESC
                LIMIT :limit
                """
            ),
            {
                "query_embedding": vector_literal,
                "query": query,
                "user_id": user_id,
                "limit": limit,
            },
        )
    ).mappings()
    return tuple(_row_to_result(cast(Mapping[str, Any], row), query) for row in rows)


async def text_search(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    limit: int = 10,
) -> tuple[SearchResult, ...]:
    rows = (
        await session.execute(
            text(
                """
                WITH text_matches AS (
                    SELECT
                        dc.document_id,
                        MAX(
                            ts_rank_cd(
                                to_tsvector('english', dc.text),
                                plainto_tsquery('english', :query)
                            )
                        ) AS text_rank,
                        COUNT(*) AS matching_chunk_count
                    FROM document_chunks dc
                    WHERE dc.user_id = :user_id
                      AND to_tsvector('english', dc.text) @@ plainto_tsquery('english', :query)
                    GROUP BY dc.document_id
                )
                SELECT
                    d.id AS document_id,
                    d.title,
                    d.mime_type,
                    d.status,
                    d.document_metadata,
                    s.kind AS source_kind,
                    s.display_name AS source_display_name,
                    s.source_metadata,
                    text_matches.text_rank,
                    text_matches.matching_chunk_count
                FROM text_matches
                JOIN documents d ON d.id = text_matches.document_id
                JOIN sources s ON s.id = d.source_id AND s.user_id = :user_id
                WHERE d.user_id = :user_id
                  AND d.status != 'deleted'
                ORDER BY text_matches.text_rank DESC, d.updated_at DESC
                LIMIT :limit
                """
            ),
            {
                "query": query,
                "user_id": user_id,
                "limit": limit,
            },
        )
    ).mappings()
    return tuple(_text_row_to_result(cast(Mapping[str, Any], row), query) for row in rows)


def _row_to_result(row: Mapping[str, Any], query: str) -> SearchResult:
    semantic_score = max(0.0, 1.0 - float(row["cosine_distance"]))
    text_score = min(float(row["text_rank"] or 0.0), 1.0)
    score = (semantic_score * 0.82) + (text_score * 0.18)
    excerpts = tuple(_excerpt(str(item), query) for item in list(row["excerpts"] or [])[:3])
    metadata = dict(row["document_metadata"] or {})
    source_metadata = {
        "kind": str(row["source_kind"]),
        "display_name": row["source_display_name"],
        "metadata": row["source_metadata"] or {},
        "document_metadata": {
            **metadata,
            "indexing_status": str(row["status"]),
        },
    }
    if str(row["source_kind"]) == "google_drive":
        source_metadata["drive"] = {
            "file_id": metadata.get("google_drive_file_id"),
            "web_url": metadata.get("drive_web_url"),
            "mime_type": metadata.get("drive_mime_type"),
            "modified_time": metadata.get("modified_time"),
        }
    return SearchResult(
        document_id=row["document_id"],
        title=str(row["title"]),
        type=row["mime_type"],
        score=round(score, 6),
        matching_excerpts=excerpts,
        source_metadata=source_metadata,
        explanation={
            "semantic_score": round(semantic_score, 6),
            "text_score": round(text_score, 6),
            "weights": {"semantic": 0.82, "text": 0.18},
            "signals": ["chunk_embedding_cosine_similarity", "chunk_text_match"],
        },
    )


def _text_row_to_result(row: Mapping[str, Any], _query: str) -> SearchResult:
    text_score = min(float(row["text_rank"] or 0.0), 1.0)
    metadata = dict(row["document_metadata"] or {})
    source_metadata = {
        "kind": str(row["source_kind"]),
        "display_name": row["source_display_name"],
        "metadata": row["source_metadata"] or {},
        "document_metadata": {
            **metadata,
            "indexing_status": str(row["status"]),
        },
    }
    if str(row["source_kind"]) == "google_drive":
        source_metadata["drive"] = {
            "file_id": metadata.get("google_drive_file_id"),
            "web_url": metadata.get("drive_web_url"),
            "mime_type": metadata.get("drive_mime_type"),
            "modified_time": metadata.get("modified_time"),
        }
    return SearchResult(
        document_id=row["document_id"],
        title=str(row["title"]),
        type=row["mime_type"],
        score=round(text_score, 6),
        matching_excerpts=(),
        source_metadata=source_metadata,
        explanation={
            "semantic_score": 0.0,
            "text_score": round(text_score, 6),
            "weights": {"semantic": 0.0, "text": 1.0},
            "signals": ["chunk_text_match"],
        },
    )


def _excerpt(text_value: str, query: str, radius: int = 180) -> str:
    lower = text_value.lower()
    terms = [term.lower() for term in query.split() if len(term) > 2]
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    if positions:
        center = min(positions)
        start = max(center - radius, 0)
        end = min(center + radius, len(text_value))
        return text_value[start:end].strip()
    return text_value[: radius * 2].strip()
