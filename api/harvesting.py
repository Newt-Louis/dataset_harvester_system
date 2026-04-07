import json,os
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from schemas.payloads import HarvesterRequest, HarvesterResponse
from services.llm_engine import run_harvester_engine
from database.database import get_db
from database import models
from core import security
from services.storage_service import StorageManager

router = APIRouter(prefix="/api/harvesting", tags=["Harvesting"])

@router.get("")
async def get_harvester_state(db: Session = Depends(get_db), current_user: models.User = Depends(security.get_current_user)):
    state = db.query(models.HarvesterState).filter(models.HarvesterState.user_id == current_user.id).first()
    if not state:
        return {}

    return {
        "prompt": state.prompt,
        "seeds": state.seeds,
        "output_format": state.output_format,
        "output_schema": state.output_schema,
        "samples": state.samples,
        "delay": state.delay
    }

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

    state = db.query(models.HarvesterState).filter(models.HarvesterState.user_id == current_user.id).first()
    if not state:
        state = models.HarvesterState(user_id=current_user.id)
        db.add(state)

    # Đóng gói Role và Constraints thành 1 JSON để lưu vào cột "prompt"
    prompt_json = json.dumps({
        "role_prompt": request_data.role_prompt,
        "constraints_prompt": request_data.constraints_prompt
    }, ensure_ascii=False)

    # Đóng gói mảng seeds thành JSON để lưu vào cột "seeds"
    seeds_json = json.dumps([seed.model_dump() for seed in request_data.seeds], ensure_ascii=False)

    state.prompt = prompt_json
    state.seeds = seeds_json
    state.output_format = request_data.format
    state.output_schema = request_data.schema_definition
    state.samples = request_data.samples
    state.delay = request_data.delay
    db.commit()

    old_jobs = db.query(models.HarvestJob).filter(models.HarvestJob.user_id == current_user.id).all()
    for oj in old_jobs:
        StorageManager.delete_job_files(current_user.username or f"user_{current_user.id}", oj.id)
        db.delete(oj)
    db.commit()

    new_job = models.HarvestJob(
        user_id=current_user.id,
        total_seeds=len(request_data.seeds),
        target_samples_per_seed=request_data.samples,
        output_format=request_data.format,
        prompt=prompt_json,
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

@router.post("/stop-harves")
async def stop_harvesting(db: Session = Depends(get_db), current_user: models.User = Depends(security.get_current_user)):
    # Tìm Job đang chạy hoặc đang chờ của User này
    active_job = db.query(models.HarvestJob).filter(
        models.HarvestJob.user_id == current_user.id,
        models.HarvestJob.status.in_(["pending", "running"])
    ).first()

    if not active_job:
        return HarvesterResponse(status="info",message="Không có tác vụ nào đang chạy để dừng.",job_id=None)

    # Đánh dấu là đã dừng. Engine chạy nền sẽ check trạng thái này và tự ngắt
    active_job.status = "stopped"
    db.commit()

    return HarvesterResponse(status="success",message="Dừng chương trình thành công. Dữ liệu đã thu thập được đã được lưu lại.",job_id=None)

@router.get("/jobs/{job_id}/download")
async def download_job_result(job_id: int, format: str = "jsonl", db: Session = Depends(get_db), current_user: models.User = Depends(security.get_current_user)):
    # Kiểm tra Job có thuộc về User này không
    job = db.query(models.HarvestJob).filter(models.HarvestJob.id == job_id, models.HarvestJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu thu hoạch này.")

    # Đường dẫn file cục bộ theo username
    username = current_user.username or f"user_{current_user.id}"
    file_path = f"downloads/{username}/dataset_job_{job_id}.{format}"

    if not os.path.exists(file_path):
        # Nếu không có file cục bộ, có thể do đã upload lên cloud và xóa local hoặc chưa sinh
        if job.output_file_url and job.output_file_url.startswith("http"):
             return {"message": "Tải từ Cloud", "url": job.output_file_url}
        raise HTTPException(status_code=404, detail="File kết quả chưa được tạo hoặc đã bị xóa.")

    return FileResponse(
        path=file_path,
        filename=f"dataset_harvest_{job_id}.{format}",
        media_type='application/octet-stream'
    )