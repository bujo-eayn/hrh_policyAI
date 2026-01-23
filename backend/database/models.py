"""
SQLAlchemy ORM models for HRH-PolicyAI database.
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from backend.database.connection import Base
from pgvector.sqlalchemy import Vector


class User(Base):
    """User model for authentication and authorization."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), nullable=False, default="user", index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    documents = relationship("Document", back_populates="uploader", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Document(Base):
    """Document model for policy documents."""
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    regulatory_body = Column(String(100), nullable=False, index=True)
    file_path = Column(String(1000))
    file_type = Column(String(50))
    file_size = Column(Integer)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    doc_metadata = Column('metadata', JSONB)
    is_processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)

    # Relationships
    uploader = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document {self.title} ({self.regulatory_body})>"


class DocumentChunk(Base):
    """Document chunk model with vector embeddings for RAG."""
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768))  # 1024 dimensions for mxbai-embed-large
    chunk_index = Column(Integer, nullable=False, index=True)
    doc_metadata = Column('metadata', JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<DocumentChunk {self.id} (chunk {self.chunk_index})>"
