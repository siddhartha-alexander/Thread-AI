from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def new_id() -> str:
    return str(uuid4())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User | None"] = relationship(back_populates="conversations")
    responses: Mapped[list["AIResponse"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AIResponse.created_at",
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="google")
    provider_sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    conversations: Mapped[list[Conversation]] = relationship(back_populates="user")


class AIResponse(Base):
    __tablename__ = "ai_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="responses")
    threads: Mapped[list["Thread"]] = relationship(
        back_populates="response",
        cascade="all, delete-orphan",
        order_by="Thread.created_at",
    )


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    response_id: Mapped[str] = mapped_column(ForeignKey("ai_responses.id"), nullable=False, index=True)
    selected_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    surrounding_context: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    response: Mapped[AIResponse] = relationship(back_populates="threads")
    messages: Mapped[list["ThreadMessage"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ThreadMessage.created_at",
    )


class ThreadMessage(Base):
    __tablename__ = "thread_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    thread: Mapped[Thread] = relationship(back_populates="messages")
