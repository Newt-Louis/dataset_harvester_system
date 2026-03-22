from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from database.database import get_db
from database import models
from core.settings import settings
from core.security import get_current_user

router = APIRouter(prefix="/api/logs", tags=["Logs"])


# ==========================================
# 1. HÀM KIỂM TRA QUYỀN ADMIN (Dependency)
# ==========================================
def get_admin_user(current_user: models.User = Depends(get_current_user)):
    # Tách chuỗi email từ .env thành list
    admin_emails = [email.strip() for email in settings.ADMIN_EMAILS.split(",") if email.strip()]

    if current_user.email not in admin_emails:
        # Nếu không có quyền, ném lỗi 403 (Cấm truy cập)
        raise HTTPException(status_code=403, detail="Khu vực cấm: Chỉ dành cho Quản trị viên.")

    return current_user


# ==========================================
# 2. HÀM TIỆN ÍCH ĐỂ GHI LOG (Dùng nội bộ)
# ==========================================
def write_system_log(db: Session, level: str, source: str, message: str):
    """
    Sử dụng hàm này trong các file khác (như llm_engine.py) để ghi lỗi vào DB.
    level: 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    """
    try:
        new_log = models.SystemLog(
            level=level.upper(),
            source=source,
            message=message,
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_log)
        db.commit()
    except Exception as e:
        print(f"LỖI KHI GHI LOG VÀO DB: {e}")


# ==========================================
# 3. ROUTE CHO FRONTEND LẤY LOGS
# ==========================================
@router.get("")
def get_system_logs(
        limit: int = 100,
        db: Session = Depends(get_db),
        admin_user: models.User = Depends(get_admin_user)  # Bắt buộc là Admin
):
    """Lấy danh sách log, sắp xếp mới nhất lên đầu"""
    logs = db.query(models.SystemLog).order_by(models.SystemLog.created_at.desc()).limit(limit).all()

    # Format lại dữ liệu trả về
    return [
        {
            "id": log.id,
            "level": log.level,
            "source": log.source,
            "message": log.message,
            "created_at": log.created_at
        } for log in logs
    ]