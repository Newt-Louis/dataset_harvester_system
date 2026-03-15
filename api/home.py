from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from database.database import get_db
from database import models
from core import security

router = APIRouter(tags=["Home"])

@router.get("/")
async def root(db: Session = Depends(get_db), current_user: models.User = Depends(security.get_optional_current_user)):
    if not current_user:
        return {
            "status": "success",
            "is_authenticated": False,
            "message": "Backend API đang hoạt động! Hãy mở http://localhost:5173 để xem giao diện UI.",
            "docs_url": "http://localhost:8000/docs"
        }

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    db.query(models.HarvestJob).filter(
        models.HarvestJob.user_id == current_user.id,
        models.HarvestJob.updated_at < yesterday
    ).delete()

    db.commit()

    jobs = db.query(models.HarvestJob).filter(
        models.HarvestJob.user_id == current_user.id
    ).order_by(models.HarvestJob.created_at.desc()).limit(10).all()

    return {
        "status": "success",
        "is_authenticated": True,
        "jobs": jobs
    }

@router.delete("/api/dashboard/cleanup")
def force_cleanup_jobs(db: Session = Depends(get_db), current_user: models.User = Depends(security.get_current_user)):
    """Xóa SẠCH toàn bộ lịch sử trạng thái của user này ngay lập tức"""
    db.query(models.HarvestJob).filter(models.HarvestJob.user_id == current_user.id).delete()
    db.commit()
    return {"status": "success", "message": "Đã xóa sạch lịch sử trên Dashboard"}