from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional

from backend.database.connection import get_db
from backend.models.schemas import ChatQuery, ChatResponse, PolicyComparisonQuery, PolicyComparisonResponse
from backend.services.auth import get_current_user
from backend.services.rag_pipeline import rag_pipeline
from backend.database.models import User
from backend.config import settings

router = APIRouter(prefix="/chat", tags=["Chat"])

# --- Security: Internal Service Communication ---
async def verify_api_key(x_api_key: str = Header(None)):
    """
    Verify the Shared Secret Key.
    Allows the Workforce Registry to call this API without a user login.
    """
    # Default key for development if not set in .env
    expected_key = getattr(settings, "CHATBOT_API_KEY", "hrh_registry_secret_key_2026")
    
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid Service API Key")
    return x_api_key

# --- Routes ---

@router.post("/query", response_model=ChatResponse)
async def chat_query(
    query: ChatQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Standard Chat: Requires User Login (For direct frontend access)."""
    try:
        return await rag_pipeline.query(
            db=db,
            query=query.query,
            regulatory_body=query.regulatory_body,
            top_k=query.top_k,
            include_sources=query.include_sources,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Query failed: {e}")


@router.post("/internal", response_model=ChatResponse, tags=["Integration"])
async def internal_chat_query(
    query: ChatQuery,
    api_key: str = Depends(verify_api_key), # <--- USES API KEY, NOT USER
    db: Session = Depends(get_db),
):
    """
    Internal Chat: For the Workforce Registry to call.
    Bypasses user login and validates the X-API-Key header.
    """
    try:
        return await rag_pipeline.query(
            db=db,
            query=query.query,
            regulatory_body=query.regulatory_body,
            top_k=query.top_k,
            include_sources=query.include_sources,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Internal query failed: {e}")


@router.post("/compare", response_model=PolicyComparisonResponse)
async def compare_policies(
    query: PolicyComparisonQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return await rag_pipeline.compare_policies(
            db=db,
            query=query.query,
            regulatory_bodies=query.regulatory_bodies,
            top_k_per_body=query.top_k_per_body,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Comparison failed: {e}")