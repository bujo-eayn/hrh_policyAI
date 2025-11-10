"""
API routes for HRH-PolicyAI.
Includes authentication, document management, chat, and admin endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import os
import uuid
from pathlib import Path

from backend.database.connection import get_db
from backend.database.models import User, Document, DocumentChunk
from backend.models.schemas import (
    UserCreate, UserLogin, UserResponse, Token, RefreshTokenRequest,
    DocumentUpload, DocumentResponse, ChatQuery, ChatResponse,
    PolicyComparisonQuery, PolicyComparisonResponse, SystemStats,
    UserListResponse
)
from backend.services.auth import (
    hash_password, authenticate_user, create_tokens, verify_token,
    get_current_user, require_admin
)
from backend.services.rag_pipeline import rag_pipeline
from backend.services.document_processor import document_processor
from backend.services.embeddings import embedding_service
from backend.config import settings


router = APIRouter()


# ============================================================================
# Authentication Routes
# ============================================================================

@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user
    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name,
        role="user"  # Default role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login and receive JWT tokens."""
    user = authenticate_user(db, credentials.email, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Create tokens
    tokens = create_tokens(str(user.id), user.email, user.role)

    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer"
    }


@router.post("/auth/refresh", response_model=Token)
async def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Refresh access token using refresh token."""
    # Verify refresh token
    token_data = verify_token(request.refresh_token, token_type="refresh")

    # Get user
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    # Create new tokens
    tokens = create_tokens(str(user.id), user.email, user.role)

    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer"
    }


@router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user


# ============================================================================
# Document Management Routes
# ============================================================================

@router.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    regulatory_body: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Upload and process a policy document (admin only)."""
    # Validate file type
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed: {', '.join(settings.ALLOWED_FILE_TYPES)}"
        )

    # Validate regulatory body
    if regulatory_body not in settings.REGULATORY_BODIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regulatory body. Allowed: {', '.join(settings.REGULATORY_BODIES)}"
        )

    # Save file
    file_id = str(uuid.uuid4())
    file_name = f"{file_id}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, file_name)

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    file_size = len(content)

    # Create document record
    document = Document(
        title=title,
        regulatory_body=regulatory_body,
        file_path=file_path,
        file_type=file_ext,
        file_size=file_size,
        uploaded_by=current_user.id
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    # Process document asynchronously (in production, use background task)
    try:
        processed_data = document_processor.process_document(file_path)

        # Create chunks with embeddings
        for chunk_data in processed_data["chunks"]:
            # Generate embedding
            embedding = await embedding_service.generate_embedding(chunk_data["content"])

            # Create chunk record
            chunk = DocumentChunk(
                document_id=document.id,
                content=chunk_data["content"],
                embedding=embedding,
                chunk_index=chunk_data["chunk_index"],
                metadata={"token_count": chunk_data.get("token_count", 0)}
            )
            db.add(chunk)

        # Mark document as processed
        document.is_processed = True
        document.processed_at = datetime.utcnow()

        db.commit()
        db.refresh(document)

    except Exception as e:
        # Clean up on error
        db.delete(document)
        db.commit()
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {str(e)}"
        )

    return document


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    regulatory_body: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all documents, optionally filtered by regulatory body."""
    query = db.query(Document)

    if regulatory_body:
        query = query.filter(Document.regulatory_body == regulatory_body)

    documents = query.order_by(Document.uploaded_at.desc()).all()

    # Add chunk count to each document
    result = []
    for doc in documents:
        doc_dict = {
            "id": doc.id,
            "title": doc.title,
            "regulatory_body": doc.regulatory_body,
            "file_path": doc.file_path,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "uploaded_by": doc.uploaded_by,
            "uploaded_at": doc.uploaded_at,
            "is_processed": doc.is_processed,
            "processed_at": doc.processed_at,
            "chunk_count": len(doc.chunks)
        }
        result.append(doc_dict)

    return result


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document details by ID."""
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    return {
        **document.__dict__,
        "chunk_count": len(document.chunks)
    }


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a document (admin only)."""
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    # Delete file
    if document.file_path and os.path.exists(document.file_path):
        os.remove(document.file_path)

    # Delete from database (chunks will be cascade deleted)
    db.delete(document)
    db.commit()


# ============================================================================
# Chat/RAG Routes
# ============================================================================

@router.post("/chat/query", response_model=ChatResponse)
async def chat_query(
    query: ChatQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ask a question about policies using RAG."""
    try:
        result = await rag_pipeline.query(
            db=db,
            query=query.query,
            regulatory_body=query.regulatory_body,
            top_k=query.top_k,
            include_sources=query.include_sources
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}"
        )


@router.post("/chat/compare", response_model=PolicyComparisonResponse)
async def compare_policies(
    query: PolicyComparisonQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compare policies across multiple regulatory bodies."""
    try:
        result = await rag_pipeline.compare_policies(
            db=db,
            query=query.query,
            regulatory_bodies=query.regulatory_bodies,
            top_k_per_body=query.top_k_per_body
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Comparison failed: {str(e)}"
        )


# ============================================================================
# Admin Routes
# ============================================================================

@router.get("/admin/users", response_model=UserListResponse)
async def list_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all users (admin only)."""
    users = db.query(User).order_by(User.created_at.desc()).all()

    return {
        "users": users,
        "total": len(users)
    }


@router.get("/admin/stats", response_model=SystemStats)
async def get_system_stats(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get system statistics (admin only)."""
    # Count totals
    total_users = db.query(User).count()
    total_documents = db.query(Document).count()
    total_chunks = db.query(DocumentChunk).count()

    # Documents by regulatory body
    docs_by_body = {}
    for body in settings.REGULATORY_BODIES:
        count = db.query(Document).filter(Document.regulatory_body == body).count()
        docs_by_body[body] = count

    # Recent uploads
    recent_docs = db.query(Document).order_by(Document.uploaded_at.desc()).limit(10).all()

    return {
        "total_users": total_users,
        "total_documents": total_documents,
        "total_chunks": total_chunks,
        "documents_by_regulatory_body": docs_by_body,
        "recent_uploads": recent_docs
    }


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION
    }
