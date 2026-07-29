from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ExtractedBlock:
    text: str
    page_number: int | None = None
    slide_number: int | None = None
    heading: str | None = None
    section: str | None = None
    source_filename: str | None = None
    block_index: int = 0


@dataclass(frozen=True)
class ExtractedDocument:
    blocks: tuple[ExtractedBlock, ...]
    source_filename: str
    mime_type: str | None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks if block.text.strip())


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    token_count: int
    content_hash: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class FilePayload:
    path: Path
    content: bytes
    mime_type: str | None
