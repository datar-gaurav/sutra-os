"""Knowledge base models for RAG pipeline — documents, chunks, and embeddings."""

from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class DocumentSourceType(str, PyEnum):
    file = "file"  # Uploaded file (PDF, txt, md)
    url = "url"    # Web page URL
    text = "text"  # Raw text pasted directly


class DocumentStatus(str, PyEnum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class KnowledgeBase(Base, TimestampMixin):
    """A named collection of documents that agents can search over."""

    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class Document(Base, TimestampMixin):
    """A single source document ingested into a knowledge base."""

    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    knowledge_base_id: Mapped[str] = mapped_column(
        String, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[DocumentSourceType] = mapped_column(
        Enum(DocumentSourceType, name="documentsourcetype"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Raw extracted text — stored so we can re-chunk without re-fetching
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="documentstatus"),
        default=DocumentStatus.pending,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base, TimestampMixin):
    """A chunked passage from a document with its embedding vector."""

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        String, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON-encoded list[float] — same pattern as Memory.embedding
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="chunks")
