import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser, get_current_user, require_matching_user
from app.core.settings import Settings, get_settings
from app.db.session import get_session
from app.ingestion.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    GeminiEmbeddingProvider,
)
from app.search.service import semantic_search, text_search

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    user_id: uuid.UUID | None = None
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResponse(BaseModel):
    query: str
    results: list[dict[str, object]]


def get_embedding_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbeddingProvider:
    return GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )


@router.post("", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchResponse:
    require_matching_user(authenticated, request.user_id)
    try:
        embedding_provider = get_embedding_provider(settings)
        results = await semantic_search(
            session=session,
            embedding_provider=embedding_provider,
            user_id=authenticated.id,
            query=request.query,
            limit=request.limit,
            settings=settings,
        )
    except (EmbeddingProviderError, ValueError):
        logger.warning(
            "Semantic embedding provider unavailable; using text search fallback",
            exc_info=True,
        )
        results = await text_search(
            session=session,
            user_id=authenticated.id,
            query=request.query,
            limit=request.limit,
            settings=settings,
        )
    return SearchResponse(
        query=request.query,
        results=[
            {
                "document_id": str(item.document_id),
                "title": item.title,
                "type": item.type,
                "score": item.score,
                "matching_excerpts": list(item.matching_excerpts),
                "source_metadata": item.source_metadata,
                "explanation": item.explanation,
            }
            for item in results
        ],
    )
