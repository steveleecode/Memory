from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Memory API"
    app_version: str = "0.1.0"
    environment: str = "development"
    enable_development_mocks: bool = Field(default=False, alias="MEMORY_ENABLE_DEVELOPMENT_MOCKS")

    database_url: str = Field(
        default="postgresql+asyncpg://memory:memory@localhost:5432/memory",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    s3_endpoint_url: str = Field(default="http://localhost:9000", alias="S3_ENDPOINT_URL")
    s3_access_key_id: str = Field(default="memory", alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="memory-secret", alias="S3_SECRET_ACCESS_KEY")
    s3_bucket: str = Field(default="memory-dev", alias="S3_BUCKET")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    embedding_model: str = Field(default="gemini-embedding-2", alias="GEMINI_EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=1536, alias="GEMINI_EMBEDDING_DIMENSIONS")
    chunk_target_tokens: int = Field(default=500, alias="MEMORY_CHUNK_TARGET_TOKENS")
    chunk_overlap_tokens: int = Field(default=80, alias="MEMORY_CHUNK_OVERLAP_TOKENS")
    search_weight_document_text: float = Field(
        default=1.0,
        alias="MEMORY_SEARCH_WEIGHT_DOCUMENT_TEXT",
    )
    search_weight_ocr_text: float = Field(default=0.88, alias="MEMORY_SEARCH_WEIGHT_OCR_TEXT")
    search_weight_filename: float = Field(default=0.72, alias="MEMORY_SEARCH_WEIGHT_FILENAME")
    search_weight_file_path: float = Field(default=0.62, alias="MEMORY_SEARCH_WEIGHT_FILE_PATH")
    search_weight_metadata: float = Field(default=0.48, alias="MEMORY_SEARCH_WEIGHT_METADATA")
    search_weight_image_caption: float = Field(
        default=0.42,
        alias="MEMORY_SEARCH_WEIGHT_IMAGE_CAPTION",
    )
    search_weight_visual_embedding: float = Field(
        default=0.24,
        alias="MEMORY_SEARCH_WEIGHT_VISUAL_EMBEDDING",
    )
    search_min_ocr_confidence: float = Field(default=0.82, alias="MEMORY_SEARCH_MIN_OCR_CONFIDENCE")
    search_strong_filename_text_rank: float = Field(
        default=0.08,
        alias="MEMORY_SEARCH_STRONG_FILENAME_TEXT_RANK",
    )
    search_min_image_single_signal_score: float = Field(
        default=0.55,
        alias="MEMORY_SEARCH_MIN_IMAGE_SINGLE_SIGNAL_SCORE",
    )
    search_include_images: bool = Field(default=False, alias="MEMORY_SEARCH_INCLUDE_IMAGES")
    local_max_upload_bytes: int = Field(
        default=32 * 1024 * 1024,
        alias="MEMORY_LOCAL_MAX_UPLOAD_BYTES",
    )
    auth_token_secret: str = Field(
        default="development-only-replace-with-random-auth-secret",
        alias="MEMORY_AUTH_TOKEN_SECRET",
    )
    auth_token_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 7,
        alias="MEMORY_AUTH_TOKEN_TTL_SECONDS",
    )
    cors_allowed_origins: list[str] = Field(
        default=[
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
            "http://127.0.0.1:5176",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://localhost:5176",
        ],
        alias="MEMORY_CORS_ALLOWED_ORIGINS",
    )

    oauth_credential_encryption_key: str = Field(
        default="development-only-replace-with-kms-managed-key",
        alias="OAUTH_CREDENTIAL_ENCRYPTION_KEY",
    )
    google_oauth_client_id: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str | None = Field(
        default=None,
        alias="GOOGLE_OAUTH_CLIENT_SECRET",
    )
    google_oauth_redirect_url: str = Field(
        default="http://127.0.0.1:8000/sources/google-drive/oauth/callback",
        alias="GOOGLE_OAUTH_REDIRECT_URL",
    )
    google_oauth_frontend_return_url: str = Field(
        default="http://127.0.0.1:5173",
        alias="GOOGLE_OAUTH_FRONTEND_RETURN_URL",
    )

    model_config = SettingsConfigDict(
        env_file=(".env", "apps/api/.env"),
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
