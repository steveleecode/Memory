"""google drive source statuses

Revision ID: 0003_drive_statuses
Revises: 0002_ingestion_search
Create Date: 2026-07-26 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_drive_statuses"
down_revision: str | None = "0002_ingestion_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for value in (
        "not_connected",
        "connecting",
        "connected",
        "syncing",
        "reauthorization_required",
        "disconnected",
    ):
        op.execute(f"ALTER TYPE source_status ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
