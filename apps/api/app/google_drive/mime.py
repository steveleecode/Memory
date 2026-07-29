from dataclasses import dataclass
from pathlib import Path

GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SLIDES = "application/vnd.google-apps.presentation"
GOOGLE_SHEETS = "application/vnd.google-apps.spreadsheet"
GOOGLE_DRAWING = "application/vnd.google-apps.drawing"

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
PLAIN_TEXT = "text/plain"
MARKDOWN = "text/markdown"
CSV = "text/csv"

SUPPORTED_DOWNLOAD_MIME_TYPES = {
    PDF,
    DOCX,
    PPTX,
    PLAIN_TEXT,
    MARKDOWN,
    "text/x-markdown",
    CSV,
    "text/tab-separated-values",
    "application/json",
}

SOURCE_CODE_EXTENSIONS = {
    ".c",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".kt",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}

METADATA_ONLY_MIME_PREFIXES = ("image/", "model/")


@dataclass(frozen=True)
class ContentPlan:
    supported: bool
    action: str
    ingest_mime_type: str | None
    filename_suffix: str
    reason: str | None = None


def content_plan(filename: str, mime_type: str | None) -> ContentPlan:
    if mime_type == GOOGLE_DOC:
        return ContentPlan(True, "export", DOCX, ".docx")
    if mime_type == GOOGLE_SLIDES:
        return ContentPlan(True, "export", PPTX, ".pptx")
    if mime_type == GOOGLE_SHEETS:
        return ContentPlan(True, "export", CSV, ".csv")
    if mime_type == GOOGLE_DRAWING:
        return ContentPlan(True, "export", PDF, ".pdf")
    if mime_type in SUPPORTED_DOWNLOAD_MIME_TYPES:
        return ContentPlan(True, "download", mime_type, Path(filename).suffix)
    if Path(filename).suffix.lower() in SOURCE_CODE_EXTENSIONS:
        return ContentPlan(True, "download", mime_type or PLAIN_TEXT, Path(filename).suffix)
    if mime_type and mime_type.startswith(METADATA_ONLY_MIME_PREFIXES):
        return ContentPlan(True, "metadata", "text/plain", ".txt")
    return ContentPlan(False, "skip", None, "", "unsupported Google Drive MIME type")


def content_filename(filename: str, plan: ContentPlan) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == plan.filename_suffix or not plan.filename_suffix:
        return filename
    return f"{filename}{plan.filename_suffix}"
