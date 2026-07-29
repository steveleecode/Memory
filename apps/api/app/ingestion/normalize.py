import re

from app.ingestion.models import ExtractedBlock, ExtractedDocument

_SPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINE_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(_SPACE_RE.sub(" ", line).strip() for line in text.split("\n"))
    return _BLANK_LINE_RE.sub("\n\n", text).strip()


def normalize_document(document: ExtractedDocument) -> ExtractedDocument:
    blocks: list[ExtractedBlock] = []
    for block in document.blocks:
        normalized = normalize_text(block.text)
        if normalized:
            blocks.append(
                ExtractedBlock(
                    text=normalized,
                    page_number=block.page_number,
                    slide_number=block.slide_number,
                    heading=block.heading,
                    section=block.section,
                    source_filename=block.source_filename or document.source_filename,
                    block_index=block.block_index,
                )
            )
    return ExtractedDocument(
        blocks=tuple(blocks),
        source_filename=document.source_filename,
        mime_type=document.mime_type,
        metadata=document.metadata,
    )
