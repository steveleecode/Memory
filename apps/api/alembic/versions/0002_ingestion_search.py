"""ingestion search

Revision ID: 0002_ingestion_search
Revises: 0001_initial_foundation
Create Date: 2026-07-25 23:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_ingestion_search"
down_revision: str | None = "0001_initial_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ingestion_job_status = postgresql.ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    name="ingestion_job_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE ingestion_job_status AS ENUM "
        "('pending', 'running', 'succeeded', 'failed', 'skipped')"
    )
    op.add_column("documents", sa.Column("searchable_text", sa.Text(), nullable=True))
    op.add_column(
        "documents", sa.Column("indexed_content_hash", sa.String(length=128), nullable=True)
    )
    op.add_column("documents", sa.Column("ingestion_error", sa.Text(), nullable=True))
    op.create_index("ix_documents_indexed_content_hash", "documents", ["indexed_content_hash"])

    op.add_column(
        "document_chunks", sa.Column("content_hash", sa.String(length=128), nullable=True)
    )
    op.execute("UPDATE document_chunks SET content_hash = md5(text)")
    op.alter_column("document_chunks", "content_hash", nullable=False)
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"])
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_text_gin "
        "ON document_chunks USING gin (to_tsvector('english', text))"
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("status", ingestion_job_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_jobs_content_hash", "ingestion_jobs", ["content_hash"])
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index("ix_ingestion_jobs_user_id", "ingestion_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_user_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_content_hash", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_text_gin")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_column("document_chunks", "content_hash")
    op.drop_index("ix_documents_indexed_content_hash", table_name="documents")
    op.drop_column("documents", "ingestion_error")
    op.drop_column("documents", "indexed_content_hash")
    op.drop_column("documents", "searchable_text")
    op.execute("DROP TYPE ingestion_job_status")
