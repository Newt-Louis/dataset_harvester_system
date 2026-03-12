from fastapi import APIRouter

router = APIRouter(tags=["Home"])

@router.get("/")
async def root():
    return {
        "status": "success",
        "message": "Backend API đang hoạt động! Hãy mở http://localhost:5173 để xem giao diện UI.",
        "docs_url": "http://localhost:8000/docs"
    }