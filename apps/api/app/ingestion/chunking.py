import re
from collections.abc import Callable, Iterable
from dataclasses import replace

import tiktoken

from app.ingestion.hashing import sha256_text
from app.ingestion.models import Chunk, ExtractedBlock, ExtractedDocument


class TokenCounter:
    def __init__(self, model: str) -> None:
        try:
            encoding = tiktoken.encoding_for_model(model)
            self._count: Callable[[str], int] = lambda text: len(encoding.encode(text))
        except Exception:
            self._count = _estimate_tokens

    def count(self, text: str) -> int:
        return self._count(text)


def _estimate_tokens(text: str) -> int:
    words = re.findall(r"\w+|[^\w\s]", text)
    return max(1, int(len(words) * 1.3))


def chunk_document(
    document: ExtractedDocument,
    *,
    model: str,
    target_tokens: int,
    overlap_tokens: int,
) -> tuple[Chunk, ...]:
    counter = TokenCounter(model)
    chunks: list[Chunk] = []
    ordinal = 0
    current: list[ExtractedBlock] = []
    current_tokens = 0

    for block in document.blocks:
        block_tokens = max(counter.count(block.text), 1)
        if current and current_tokens + block_tokens > target_tokens:
            chunks.append(_make_chunk(ordinal, current, counter))
            ordinal += 1
            current = _overlap_blocks(current, counter, overlap_tokens)
            current_tokens = sum(counter.count(item.text) for item in current)
        if block_tokens > target_tokens:
            for piece in _split_large_block(block, counter, target_tokens, overlap_tokens):
                if current:
                    chunks.append(_make_chunk(ordinal, current, counter))
                    ordinal += 1
                    current = []
                    current_tokens = 0
                chunks.append(_make_chunk(ordinal, [piece], counter))
                ordinal += 1
            continue
        current.append(block)
        current_tokens += block_tokens

    if current:
        chunks.append(_make_chunk(ordinal, current, counter))
    return tuple(chunks)


def _make_chunk(ordinal: int, blocks: Iterable[ExtractedBlock], counter: TokenCounter) -> Chunk:
    block_list = list(blocks)
    text = "\n\n".join(block.text for block in block_list)
    headings = sorted({block.heading for block in block_list if block.heading})
    sections = sorted({block.section for block in block_list if block.section})
    pages = sorted({block.page_number for block in block_list if block.page_number is not None})
    slides = sorted({block.slide_number for block in block_list if block.slide_number is not None})
    filenames = sorted({block.source_filename for block in block_list if block.source_filename})
    metadata: dict[str, object] = {
        "headings": headings,
        "sections": sections,
        "page_numbers": pages,
        "slide_numbers": slides,
        "source_filenames": filenames,
        "block_indexes": [block.block_index for block in block_list],
    }
    return Chunk(
        ordinal=ordinal,
        text=text,
        token_count=counter.count(text),
        content_hash=sha256_text(text),
        metadata=metadata,
    )


def _overlap_blocks(
    blocks: list[ExtractedBlock],
    counter: TokenCounter,
    overlap_tokens: int,
) -> list[ExtractedBlock]:
    if overlap_tokens <= 0:
        return []
    selected: list[ExtractedBlock] = []
    total = 0
    for block in reversed(blocks):
        block_tokens = counter.count(block.text)
        if selected and total + block_tokens > overlap_tokens:
            break
        selected.append(block)
        total += block_tokens
    return list(reversed(selected))


def _split_large_block(
    block: ExtractedBlock,
    counter: TokenCounter,
    target_tokens: int,
    overlap_tokens: int,
) -> tuple[ExtractedBlock, ...]:
    words = block.text.split()
    pieces: list[ExtractedBlock] = []
    current: list[str] = []
    piece_index = 0

    for word in words:
        candidate = [*current, word]
        candidate_tokens = counter.count(" ".join(candidate))
        if current and candidate_tokens > target_tokens:
            pieces.append(
                replace(
                    block,
                    text=" ".join(current),
                    block_index=block.block_index + piece_index,
                )
            )
            piece_index += 1
            overlap_words = _last_words_within_tokens(current, counter, overlap_tokens)
            current = overlap_words
        current.append(word)

    if current:
        pieces.append(
            replace(block, text=" ".join(current), block_index=block.block_index + piece_index)
        )
    return tuple(pieces)


def _last_words_within_tokens(
    words: list[str],
    counter: TokenCounter,
    max_tokens: int,
) -> list[str]:
    if max_tokens <= 0:
        return []
    selected: list[str] = []
    for word in reversed(words):
        candidate = [word, *selected]
        if counter.count(" ".join(candidate)) > max_tokens:
            break
        selected.insert(0, word)
    return selected
