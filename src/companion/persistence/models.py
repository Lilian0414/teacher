from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from companion.persistence.database import Base


class AvailabilityOverride(Base):
    __tablename__ = "availability_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    starts_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32))


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="text")
    private_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[str] = mapped_column(String(40), index=True)
    ended_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16), default="terminal")
    created_at: Mapped[str] = mapped_column(String(40), index=True)


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("canonical_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(256, collation="NOCASE"))
    aliases: Mapped[str] = mapped_column(Text, default="[]")
    relationship_to_user: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40))


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    person_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("people.id"),
        nullable=True,
        index=True,
    )
    source_conversation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("conversations.id"),
        nullable=True,
        index=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40))
