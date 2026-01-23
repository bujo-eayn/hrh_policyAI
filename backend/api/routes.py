from fastapi import APIRouter
from backend.config import settings

# USE RELATIVE IMPORTS (The dot . means "current folder")
from .auth import router as auth_router
from .documents import router as documents_router
from .chat import router as chat_router
from .admin import router as admin_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(documents_router)
router.include_router(chat_router)
router.include_router(admin_router)

@router.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION
    }