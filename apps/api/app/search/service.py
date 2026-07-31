import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
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
    settings: Settings | None = None,
) -> tuple[SearchResult, ...]:
    search_settings = settings or Settings()
    query_embedding = (await embedding_provider.embed_texts([query]))[0]
    vector_literal = "[" + ",".join(str(float(value)) for value in query_embedding) + "]"
    rows = (
        await session.execute(
            text(
                """
                WITH representation_matches AS (
                    SELECT
                        sr.document_id,
                        sr.id AS representation_id,
                        sr.chunk_id,
                        sr.representation_type::text AS representation_type,
                        sr.mime_type AS representation_mime_type,
                        sr.source_content,
                        sr.source_confidence,
                        sr.embedding_model,
                        sr.embedding_model_version,
                        sr.extractor_version,
                        sr.created_at AS representation_created_at,
                        sr.representation_metadata,
                        sr.embedding <=> CAST(:query_embedding AS vector) AS cosine_distance,
                        ts_rank_cd(
                            to_tsvector('english', sr.source_content),
                            plainto_tsquery('english', :query)
                        ) AS text_rank,
                        CASE sr.representation_type::text
                            WHEN 'document_text'
                                THEN CAST(:weight_document_text AS double precision)
                            WHEN 'ocr_text' THEN CAST(:weight_ocr_text AS double precision)
                            WHEN 'filename' THEN CAST(:weight_filename AS double precision)
                            WHEN 'file_path' THEN CAST(:weight_file_path AS double precision)
                            WHEN 'metadata' THEN CAST(:weight_metadata AS double precision)
                            WHEN 'image_caption'
                                THEN CAST(:weight_image_caption AS double precision)
                            WHEN 'visual_embedding'
                                THEN CAST(:weight_visual_embedding AS double precision)
                            ELSE CAST(:weight_metadata AS double precision)
                        END AS configured_weight
                    FROM search_representations sr
                    WHERE sr.user_id = :user_id
                      AND sr.embedding IS NOT NULL
                ),
                scored_signals AS (
                    SELECT
                        *,
                        GREATEST(0.0, 1.0 - cosine_distance) AS semantic_score,
                        LEAST(COALESCE(text_rank, 0), 1.0) AS text_score,
                        CASE
                            WHEN representation_type IN ('filename', 'file_path')
                                 AND COALESCE(text_rank, 0)
                                     >= CAST(:strong_filename_text_rank AS double precision)
                                THEN GREATEST(
                                    configured_weight,
                                    CAST(:weight_filename AS double precision)
                                )
                            WHEN representation_type = 'ocr_text'
                                 AND COALESCE(source_confidence, 0)
                                     < CAST(:min_ocr_confidence AS double precision)
                                THEN LEAST(
                                    configured_weight,
                                    CAST(:low_ocr_weight AS double precision)
                                )
                            WHEN representation_type = 'image_caption'
                                 AND lower(source_content) IN (
                                    'image',
                                    'photo',
                                    'screenshot',
                                    'picture',
                                    'untitled image',
                                    'screen shot'
                                 )
                                THEN LEAST(
                                    configured_weight,
                                    CAST(:generic_caption_weight AS double precision)
                                )
                            ELSE configured_weight
                        END AS applied_weight,
                        array_remove(ARRAY[
                            CASE
                                WHEN representation_type = 'ocr_text'
                                     AND COALESCE(source_confidence, 0)
                                         < CAST(:min_ocr_confidence AS double precision)
                                    THEN 'low_confidence_ocr'
                            END,
                            CASE
                                WHEN representation_type = 'image_caption'
                                     AND lower(source_content) IN (
                                        'image',
                                        'photo',
                                        'screenshot',
                                        'picture',
                                        'untitled image',
                                        'screen shot'
                                     )
                                    THEN 'generic_image_caption'
                            END
                        ], NULL) AS adjustments
                    FROM representation_matches
                ),
                ranked_signals AS (
                    SELECT
                        *,
                        (
                            (semantic_score * CAST(:semantic_weight AS double precision))
                            + (text_score * CAST(:text_weight AS double precision))
                        ) * applied_weight AS signal_score
                    FROM scored_signals
                ),
                document_matches AS (
                    SELECT
                        document_id,
                        MAX(signal_score) AS final_score,
                        COUNT(*) AS signal_count,
                        (array_agg(source_content ORDER BY signal_score DESC))[1:3] AS excerpts,
                        (array_agg(representation_type ORDER BY signal_score DESC))[1]
                            AS matched_representation_type,
                        jsonb_agg(
                            jsonb_build_object(
                                'representation_id', representation_id::text,
                                'chunk_id', chunk_id::text,
                                'type', representation_type,
                                'score', signal_score,
                                'raw_semantic_score', semantic_score,
                                'raw_text_score', text_score,
                                'matched_content', source_content,
                                'source_confidence', source_confidence,
                                'embedding_model', embedding_model,
                                'embedding_model_version', embedding_model_version,
                                'extractor_version', extractor_version,
                                'created_at', representation_created_at,
                                'applied_weight', applied_weight,
                                'configured_weight', configured_weight,
                                'adjustments', adjustments,
                                'metadata', representation_metadata
                            )
                            ORDER BY signal_score DESC
                        ) AS signals
                    FROM ranked_signals
                    GROUP BY document_id
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
                    document_matches.final_score,
                    document_matches.signal_count,
                    document_matches.excerpts,
                    document_matches.matched_representation_type,
                    document_matches.signals
                FROM document_matches
                JOIN documents d ON d.id = document_matches.document_id
                JOIN sources s ON s.id = d.source_id AND s.user_id = :user_id
                WHERE d.user_id = :user_id
                  AND d.status != 'deleted'
                  AND NOT (
                    d.mime_type LIKE 'image/%'
                    AND document_matches.signal_count = 1
                    AND document_matches.final_score
                        < CAST(:min_image_single_signal_score AS double precision)
                  )
                ORDER BY document_matches.final_score DESC, d.updated_at DESC
                LIMIT :limit
                """
            ),
            {
                **_search_params(search_settings),
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
    settings: Settings | None = None,
) -> tuple[SearchResult, ...]:
    search_settings = settings or Settings()
    rows = (
        await session.execute(
            text(
                """
                WITH text_matches AS (
                    SELECT
                        sr.document_id,
                        sr.id AS representation_id,
                        sr.chunk_id,
                        sr.representation_type::text AS representation_type,
                        sr.source_content,
                        sr.source_confidence,
                        sr.embedding_model,
                        sr.embedding_model_version,
                        sr.extractor_version,
                        sr.created_at AS representation_created_at,
                        sr.representation_metadata,
                        ts_rank_cd(
                            to_tsvector('english', sr.source_content),
                            plainto_tsquery('english', :query)
                        ) AS text_rank,
                        CASE sr.representation_type::text
                            WHEN 'document_text'
                                THEN CAST(:weight_document_text AS double precision)
                            WHEN 'ocr_text' THEN CAST(:weight_ocr_text AS double precision)
                            WHEN 'filename' THEN CAST(:weight_filename AS double precision)
                            WHEN 'file_path' THEN CAST(:weight_file_path AS double precision)
                            WHEN 'metadata' THEN CAST(:weight_metadata AS double precision)
                            WHEN 'image_caption'
                                THEN CAST(:weight_image_caption AS double precision)
                            WHEN 'visual_embedding'
                                THEN CAST(:weight_visual_embedding AS double precision)
                            ELSE CAST(:weight_metadata AS double precision)
                        END AS configured_weight
                    FROM search_representations sr
                    WHERE sr.user_id = :user_id
                      AND to_tsvector('english', sr.source_content)
                          @@ plainto_tsquery('english', :query)
                ),
                ranked_signals AS (
                    SELECT
                        *,
                        LEAST(COALESCE(text_rank, 0), 1.0) AS text_score,
                        CASE
                            WHEN representation_type IN ('filename', 'file_path')
                                 AND COALESCE(text_rank, 0)
                                     >= CAST(:strong_filename_text_rank AS double precision)
                                THEN GREATEST(
                                    configured_weight,
                                    CAST(:weight_filename AS double precision)
                                )
                            WHEN representation_type = 'ocr_text'
                                 AND COALESCE(source_confidence, 0)
                                     < CAST(:min_ocr_confidence AS double precision)
                                THEN LEAST(
                                    configured_weight,
                                    CAST(:low_ocr_weight AS double precision)
                                )
                            ELSE configured_weight
                        END AS applied_weight
                    FROM text_matches
                ),
                document_matches AS (
                    SELECT
                        document_id,
                        MAX(text_score * applied_weight) AS final_score,
                        COUNT(*) AS signal_count,
                        (
                            array_agg(
                                representation_type
                                ORDER BY text_score * applied_weight DESC
                            )
                        )[1] AS matched_representation_type,
                        jsonb_agg(
                            jsonb_build_object(
                                'representation_id', representation_id::text,
                                'chunk_id', chunk_id::text,
                                'type', representation_type,
                                'score', text_score * applied_weight,
                                'raw_semantic_score', 0.0,
                                'raw_text_score', text_score,
                                'matched_content', source_content,
                                'source_confidence', source_confidence,
                                'embedding_model', embedding_model,
                                'embedding_model_version', embedding_model_version,
                                'extractor_version', extractor_version,
                                'created_at', representation_created_at,
                                'applied_weight', applied_weight,
                                'configured_weight', configured_weight,
                                'adjustments', ARRAY[]::text[],
                                'metadata', representation_metadata
                            )
                            ORDER BY text_score * applied_weight DESC
                        ) AS signals
                    FROM ranked_signals
                    GROUP BY document_id
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
                    document_matches.final_score,
                    document_matches.signal_count,
                    ARRAY[]::text[] AS excerpts,
                    document_matches.matched_representation_type,
                    document_matches.signals
                FROM document_matches
                JOIN documents d ON d.id = document_matches.document_id
                JOIN sources s ON s.id = d.source_id AND s.user_id = :user_id
                WHERE d.user_id = :user_id
                  AND d.status != 'deleted'
                ORDER BY document_matches.final_score DESC, d.updated_at DESC
                LIMIT :limit
                """
            ),
            {
                **_search_params(search_settings),
                "query": query,
                "user_id": user_id,
                "limit": limit,
            },
        )
    ).mappings()
    return tuple(_row_to_result(cast(Mapping[str, Any], row), query) for row in rows)


def _row_to_result(row: Mapping[str, Any], query: str) -> SearchResult:
    score = float(row.get("final_score") or 0.0)
    signals = _signals(row)
    excerpts = tuple(
        _excerpt(str(item), query)
        for item in list(row.get("excerpts") or [])[:3]
        if _safe_excerpt_type(signals, str(item))
    )
    metadata = dict(row["document_metadata"] or {})
    source_metadata = _source_metadata(row, metadata)
    has_extracted_text = bool(metadata.get("has_extracted_text"))
    matched_representation_type = str(
        row.get("matched_representation_type") or _matched_type(signals) or "metadata"
    )
    text_score = max(
        (
            _float_signal(signal.get("raw_text_score"))
            for signal in signals
            if signal.get("type") in {"document_text", "ocr_text"}
        ),
        default=0.0,
    )
    semantic_score = max(
        (_float_signal(signal.get("raw_semantic_score")) for signal in signals),
        default=0.0,
    )
    return SearchResult(
        document_id=row["document_id"],
        title=str(row["title"]),
        type=row["mime_type"],
        score=round(score, 6),
        matching_excerpts=excerpts,
        source_metadata=source_metadata,
        explanation={
            "final_score": round(score, 6),
            "semantic_score": round(semantic_score, 6),
            "text_score": round(text_score, 6),
            "matched_representation_type": matched_representation_type,
            "has_extracted_text": has_extracted_text,
            "signals": signals,
        },
    )


def _signals(row: Mapping[str, Any]) -> list[dict[str, object]]:
    raw_signals = row.get("signals") or []
    if isinstance(raw_signals, list):
        return [dict(signal) for signal in raw_signals if isinstance(signal, Mapping)]
    return []


def _source_metadata(row: Mapping[str, Any], metadata: dict[str, object]) -> dict[str, object]:
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
    return source_metadata


def _matched_type(signals: list[dict[str, object]]) -> str | None:
    if not signals:
        return None
    return str(signals[0].get("type"))


def _safe_excerpt_type(signals: list[dict[str, object]], excerpt: str) -> bool:
    for signal in signals:
        if signal.get("matched_content") == excerpt:
            return signal.get("type") in {"document_text", "ocr_text", "image_caption"}
    return True


def _search_params(settings: Settings) -> dict[str, float]:
    return {
        "semantic_weight": 0.82,
        "text_weight": 0.18,
        "weight_document_text": settings.search_weight_document_text,
        "weight_ocr_text": settings.search_weight_ocr_text,
        "weight_filename": settings.search_weight_filename,
        "weight_file_path": settings.search_weight_file_path,
        "weight_metadata": settings.search_weight_metadata,
        "weight_image_caption": settings.search_weight_image_caption,
        "weight_visual_embedding": settings.search_weight_visual_embedding,
        "min_ocr_confidence": settings.search_min_ocr_confidence,
        "strong_filename_text_rank": settings.search_strong_filename_text_rank,
        "low_ocr_weight": min(settings.search_weight_ocr_text, 0.18),
        "generic_caption_weight": min(settings.search_weight_image_caption, 0.12),
        "min_image_single_signal_score": settings.search_min_image_single_signal_score,
    }


def _float_signal(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


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
