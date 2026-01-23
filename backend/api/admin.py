from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Document, DocumentChunk
from backend.models.schemas import UserListResponse, SystemStats
from backend.services.auth import require_admin
from backend.config import settings

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=UserListResponse)
async def list_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return {"users": users, "total": len(users)}


@router.get("/stats", response_model=SystemStats)
async def system_stats(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    docs_by_body = {
        body: db.query(Document).filter(Document.regulatory_body == body).count()
        for body in settings.REGULATORY_BODIES
    }

    return {
        "total_users": db.query(User).count(),
        "total_documents": db.query(Document).count(),
        "total_chunks": db.query(DocumentChunk).count(),
        "documents_by_regulatory_body": docs_by_body,
        "recent_uploads": db.query(Document).order_by(Document.uploaded_at.desc()).limit(10).all(),
    }