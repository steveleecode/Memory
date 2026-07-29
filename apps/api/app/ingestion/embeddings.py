from collections.abc import Sequence
from typing import Protocol

from google import genai
from google.genai import types


class EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        pass


class GeminiEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        dimensions: int,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for real embedding generation")
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.dimensions = dimensions

    async def embed_texts(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        import asyncio

        return [await asyncio.to_thread(self._embed_one, text) for text in texts]

    def _embed_one(self, text: str) -> tuple[float, ...]:
        response = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self.dimensions),
        )
        if not response.embeddings:
            raise ValueError("Gemini returned no embeddings")
        values = response.embeddings[0].values
        if values is None:
            raise ValueError("Gemini returned an embedding without values")
        return tuple(float(value) for value in values)


class DeterministicTestEmbeddingProvider:
    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    async def embed_texts(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> tuple[float, ...]:
        import hashlib
        import math

        values = [0.0 for _ in range(self.dimensions)]
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            values[index] += sign
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return tuple(value / norm for value in values)
