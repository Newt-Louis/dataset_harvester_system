import json
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from schemas.payloads import HarvesterRequest, HarvesterResponse
from services.llm_engine import run_harvester_engine
from database.database import get_db
from database import models
from core import security

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
        "samples": state.samples
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

    # Đóng gói Role và Constraints thành 1 cục JSON để lưu vào cột "prompt"
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
    db.commit()

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