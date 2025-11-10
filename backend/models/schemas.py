"""
Pydantic models for request/response validation.
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# ============================================================================
# Authentication Schemas
# ============================================================================

class UserCreate(BaseModel):
    """Schema for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

    @validator('password')
    def password_strength(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user data in responses."""
    id: UUID
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for data stored in JWT token."""
    user_id: str
    email: str
    role: str


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""
    refresh_token: str


# ============================================================================
# Document Schemas
# ============================================================================

class DocumentUpload(BaseModel):
    """Schema for document upload request."""
    title: str = Field(..., max_length=500)
    regulatory_body: str = Field(..., max_length=100)
    metadata: Optional[Dict[str, Any]] = None

    @validator('regulatory_body')
    def validate_regulatory_body(cls, v):
        """Validate regulatory body is in allowed list."""
        allowed = ["KMPDB", "NCK", "COC", "PPB", "PHOTC"]
        if v not in allowed:
            raise ValueError(f'Regulatory body must be one of: {", ".join(allowed)}')
        return v


class DocumentResponse(BaseModel):
    """Schema for document data in responses."""
    id: UUID
    title: str
    regulatory_body: str
    file_path: Optional[str]
    file_type: Optional[str]
    file_size: Optional[int]
    uploaded_by: Optional[UUID]
    uploaded_at: datetime
    is_processed: bool
    processed_at: Optional[datetime]
    chunk_count: Optional[int] = 0

    class Config:
        from_attributes = True


class DocumentChunkResponse(BaseModel):
    """Schema for document chunk in responses."""
    id: UUID
    document_id: UUID
    content: str
    chunk_index: int
    metadata: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


# ============================================================================
# RAG/Chat Schemas
# ============================================================================

class ChatQuery(BaseModel):
    """Schema for RAG chat query."""
    query: str = Field(..., min_length=3, max_length=2000)
    regulatory_body: Optional[str] = None
    top_k: Optional[int] = Field(default=5, ge=1, le=20)
    include_sources: bool = True

    @validator('regulatory_body')
    def validate_regulatory_body(cls, v):
        """Validate regulatory body if provided."""
        if v is not None:
            allowed = ["KMPDB", "NCK", "COC", "PPB", "PHOTC"]
            if v not in allowed:
                raise ValueError(f'Regulatory body must be one of: {", ".join(allowed)}')
        return v


class SourceDocument(BaseModel):
    """Schema for source document in RAG response."""
    document_id: UUID
    document_title: str
    regulatory_body: str
    chunk_content: str
    similarity_score: float
    chunk_index: int


class ChatResponse(BaseModel):
    """Schema for RAG chat response."""
    query: str
    answer: str
    sources: List[SourceDocument]
    regulatory_body_filter: Optional[str]
    processing_time: float
    model_used: str


class PolicyComparisonQuery(BaseModel):
    """Schema for policy comparison across regulatory bodies."""
    query: str = Field(..., min_length=3, max_length=2000)
    regulatory_bodies: List[str] = Field(..., min_items=2, max_items=5)
    top_k_per_body: int = Field(default=3, ge=1, le=10)

    @validator('regulatory_bodies')
    def validate_regulatory_bodies(cls, v):
        """Validate all regulatory bodies are in allowed list."""
        allowed = ["KMPDB", "NCK", "COC", "PPB", "PHOTC"]
        for body in v:
            if body not in allowed:
                raise ValueError(f'Each regulatory body must be one of: {", ".join(allowed)}')
        return v


class PolicyComparisonResponse(BaseModel):
    """Schema for policy comparison response."""
    query: str
    comparison: Dict[str, Any]  # Maps regulatory body to their policy excerpts
    analysis: str  # LLM-generated comparative analysis
    processing_time: float


# ============================================================================
# Admin Schemas
# ============================================================================

class UserListResponse(BaseModel):
    """Schema for list of users (admin only)."""
    users: List[UserResponse]
    total: int


class SystemStats(BaseModel):
    """Schema for system statistics."""
    total_users: int
    total_documents: int
    total_chunks: int
    documents_by_regulatory_body: Dict[str, int]
    recent_uploads: List[DocumentResponse]


# ============================================================================
# Error Schemas
# ============================================================================

class ErrorResponse(BaseModel):
    """Schema for error responses."""
    error: str
    detail: Optional[str] = None
    status_code: int
