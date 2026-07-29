import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import enum_values

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class SourceKind(StrEnum):
    GOOGLE_DRIVE = "google_drive"
    LOCAL_FOLDER = "local_folder"


class SourceStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    REVOKED = "revoked"
    NOT_CONNECTED = "not_connected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SYNCING = "syncing"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    DISCONNECTED = "disconnected"


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "external_id", name="uq_sources_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[SourceKind] = mapped_column(
        Enum(SourceKind, name="source_kind", values_callable=enum_values),
        nullable=False,
    )
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, name="source_status", values_callable=enum_values),
        nullable=False,
        default=SourceStatus.PENDING,
    )
    external_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    sync_cursor: Mapped[str | None] = mapped_column(String(4096))
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary)
    source_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="sources")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
