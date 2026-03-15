from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from schemas.payloads import HarvesterRequest, HarvesterResponse
from services.llm_engine import run_harvester_engine
from database.database import get_db
from database import models
from core import security

router = APIRouter(prefix="/api", tags=["Harvesting"])

@router.post("/generate", response_model=HarvesterResponse)
async def generate_dataset(request_data: HarvesterRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user)):
    active_keys = db.query(models.ApiConfig).filter(
        models.ApiConfig.user_id == current_user.id,
        models.ApiConfig.is_active == True
    ).count()
    if active_keys == 0:
        raise HTTPException(status_code=400, detail="Bạn chưa bật API Key nào trong phần Cấu hình!")
    total_samples_expected = request_data.samples * len(request_data.seeds)
    new_job = models.HarvestJob(
        user_id=current_user.id,
        total_seeds=len(request_data.seeds),
        target_samples_per_seed=request_data.samples,
        output_format=request_data.format,
        prompt="Dynamic Prompt Architecture",  # Lưu tóm tắt
        status="pending"
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    background_tasks.add_task(run_harvester_engine, new_job.id, request_data, current_user.id)

    return HarvesterResponse(
        status="processing",
        message=f"Hệ thống đã đưa vào hàng đợi! Dự kiến sinh tối đa {total_samples_expected} mẫu. Hãy sang Trạm Điều Khiển (Dashboard) để xem tiến độ.",
        job_id=new_job.id
    )