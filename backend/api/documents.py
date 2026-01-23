from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import os, uuid

from backend.database.connection import get_db
from backend.database.models import Document, DocumentChunk, User
from backend.models.schemas import DocumentResponse
from backend.services.auth import require_admin, get_current_user
from backend.services.document_processor import document_processor
from backend.services.embeddings import embedding_service
from backend.config import settings

router = APIRouter(prefix="/documents", tags=["Document Management"])

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    regulatory_body: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.ALLOWED_FILE_TYPES:
        raise HTTPException(400, "Invalid file type")

    if regulatory_body not in settings.REGULATORY_BODIES:
        raise HTTPException(400, "Invalid regulatory body")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_id = str(uuid.uuid4())
    file_path = os.path.join(settings.UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    document = Document(
        title=title,
        regulatory_body=regulatory_body,
        file_path=file_path,
        file_type=ext,
        file_size=len(content),
        uploaded_by=current_user.id,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        processed = document_processor.process_document(file_path)

        for chunk in processed["chunks"]:
            embedding = await embedding_service.generate_embedding(chunk["content"])
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    content=chunk["content"],
                    embedding=embedding,
                    chunk_index=chunk["chunk_index"],
                )
            )

        document.is_processed = True
        document.processed_at = datetime.utcnow()
        db.commit()
        db.refresh(document)

    except Exception as e:
        db.delete(document)
        db.commit()
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(500, f"Document processing failed: {e}")

    # Return with chunk count calculated manually
    return {**document.__dict__, "chunk_count": len(processed["chunks"])}


@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    regulatory_body: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Document)

    if regulatory_body:
        query = query.filter(Document.regulatory_body == regulatory_body)
    if search:
        query = query.filter(Document.title.ilike(f"%{search}%"))

    documents = query.offset(offset).limit(limit).all()
    
    # FIX: Calculate chunk_count for each document so the Pydantic model is happy
    return [
        {**doc.__dict__, "chunk_count": len(doc.chunks)} 
        for doc in documents
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    
    # FIX: Add chunk_count here too
    return {**doc.__dict__, "chunk_count": len(doc.chunks)}


@router.get("/{document_id}/file")
async def download_document(
    document_id: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=doc.file_path,
        filename=os.path.basename(doc.file_path),
        media_type="application/octet-stream",
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.delete(doc)
    db.commit()