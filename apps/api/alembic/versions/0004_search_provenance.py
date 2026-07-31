"""search representation provenance

Revision ID: 0004_search_provenance
Revises: 0003_drive_statuses
Create Date: 2026-07-31 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_search_provenance"
down_revision: str | None = "0003_drive_statuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

search_representation_type = postgresql.ENUM(
    "document_text",
    "ocr_text",
    "image_caption",
    "filename",
    "file_path",
    "metadata",
    "visual_embedding",
    name="search_representation_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE search_representation_type AS ENUM "
        "('document_text', 'ocr_text', 'image_caption', 'filename', 'file_path', "
        "'metadata', 'visual_embedding')"
    )
    op.create_table(
        "search_representations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("representation_type", search_representation_type, nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("source_content", sa.Text(), nullable=False),
        sa.Column("source_confidence", sa.Float(), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_model_version", sa.String(length=255), nullable=False),
        sa.Column("extractor_version", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column(
            "representation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "representation_type",
            "chunk_id",
            "content_hash",
            name="uq_search_representations_identity",
        ),
    )
    op.create_index("ix_search_representations_chunk_id", "search_representations", ["chunk_id"])
    op.create_index(
        "ix_search_representations_content_hash",
        "search_representations",
        ["content_hash"],
    )
    op.create_index(
        "ix_search_representations_document_id",
        "search_representations",
        ["document_id"],
    )
    op.create_index(
        "ix_search_representations_representation_type",
        "search_representations",
        ["representation_type"],
    )
    op.create_index("ix_search_representations_user_id", "search_representations", ["user_id"])
    op.execute(
        "ALTER TABLE search_representations ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector"
    )
    op.execute(
        "CREATE INDEX ix_search_representations_text_gin "
        "ON search_representations USING gin (to_tsvector('english', source_content))"
    )
    op.execute(
        """
        INSERT INTO search_representations (
            id,
            user_id,
            document_id,
            chunk_id,
            representation_type,
            mime_type,
            source_content,
            source_confidence,
            embedding_model,
            embedding_model_version,
            extractor_version,
            content_hash,
            embedding,
            representation_metadata
        )
        SELECT
            gen_random_uuid(),
            dc.user_id,
            dc.document_id,
            dc.id,
            'document_text'::search_representation_type,
            d.mime_type,
            dc.text,
            NULL,
            COALESCE(dc.chunk_metadata->>'embedding_model', 'legacy-unknown'),
            COALESCE(dc.chunk_metadata->>'embedding_model', 'legacy-unknown'),
            'legacy_backfill',
            dc.content_hash,
            dc.embedding,
            jsonb_build_object('legacy_backfill', true, 'chunk_metadata', dc.chunk_metadata)
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id AND d.user_id = dc.user_id
        WHERE dc.embedding IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX ix_search_representations_embedding_hnsw "
        "ON search_representations USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_search_representations_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_search_representations_text_gin")
    op.drop_index("ix_search_representations_user_id", table_name="search_representations")
    op.drop_index(
        "ix_search_representations_representation_type",
        table_name="search_representations",
    )
    op.drop_index("ix_search_representations_document_id", table_name="search_representations")
    op.drop_index("ix_search_representations_content_hash", table_name="search_representations")
    op.drop_index("ix_search_representations_chunk_id", table_name="search_representations")
    op.drop_table("search_representations")
    op.execute("DROP TYPE search_representation_type")
