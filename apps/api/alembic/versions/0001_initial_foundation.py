"""initial foundation

Revision ID: 0001_initial_foundation
Revises:
Create Date: 2026-07-25 23:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

source_kind = postgresql.ENUM(
    "google_drive",
    "local_folder",
    name="source_kind",
    create_type=False,
)
source_status = postgresql.ENUM(
    "pending",
    "active",
    "paused",
    "error",
    "revoked",
    name="source_status",
    create_type=False,
)
document_status = postgresql.ENUM(
    "discovered",
    "extracting",
    "indexed",
    "failed",
    "deleted",
    name="document_status",
    create_type=False,
)
relationship_kind = postgresql.ENUM(
    "semantic_similarity",
    "shared_source",
    "explicit_reference",
    "temporal_neighbor",
    name="relationship_kind",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE TYPE source_kind AS ENUM ('google_drive', 'local_folder')")
    op.execute(
        "CREATE TYPE source_status AS ENUM ('pending', 'active', 'paused', 'error', 'revoked')"
    )
    op.execute(
        "CREATE TYPE document_status AS ENUM "
        "('discovered', 'extracting', 'indexed', 'failed', 'deleted')"
    )
    op.execute(
        "CREATE TYPE relationship_kind AS ENUM "
        "('semantic_similarity', 'shared_source', 'explicit_reference', 'temporal_neighbor')"
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", source_kind, nullable=False),
        sa.Column("status", source_status, nullable=False),
        sa.Column("external_id", sa.String(length=1024), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("sync_cursor", sa.String(length=4096), nullable=True),
        sa.Column("encrypted_credentials", sa.LargeBinary(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "external_id", name="uq_sources_identity"),
    )
    op.create_index("ix_sources_user_id", "sources", ["user_id"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("status", document_status, nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("object_key", sa.String(length=2048), nullable=True),
        sa.Column("text_object_key", sa.String(length=2048), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("graph_x", sa.Integer(), nullable=True),
        sa.Column("graph_y", sa.Integer(), nullable=True),
        sa.Column("document_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_documents_source_external"),
    )
    op.execute(
        "ALTER TABLE documents ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_user_id", "documents", ["user_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("chunk_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_document_chunks_document_ordinal"),
    )
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector"
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_user_id", "document_chunks", ["user_id"])

    op.create_table(
        "document_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", relationship_kind, nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("relationship_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_document_id",
            "target_document_id",
            "kind",
            name="uq_document_relationships_edge",
        ),
    )
    op.create_index(
        "ix_document_relationships_source_document_id",
        "document_relationships",
        ["source_document_id"],
    )
    op.create_index(
        "ix_document_relationships_target_document_id",
        "document_relationships",
        ["target_document_id"],
    )
    op.create_index("ix_document_relationships_user_id", "document_relationships", ["user_id"])


def downgrade() -> None:
    op.drop_table("document_relationships")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("sources")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE relationship_kind")
    op.execute("DROP TYPE document_status")
    op.execute("DROP TYPE source_status")
    op.execute("DROP TYPE source_kind")
