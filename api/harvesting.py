from fastapi import APIRouter, BackgroundTasks
from schemas.payloads import HarvesterRequest, HarvesterResponse
from services.llm_engine import run_harvester_engine

router = APIRouter(prefix="/api", tags=["Harvesting"])

@router.post("/generate", response_model=HarvesterResponse)
async def generate_dataset(request_data: HarvesterRequest, background_tasks: BackgroundTasks):
    active_keys = [config for config in request_data.api_configs if config.isActive]
    if not active_keys:
        return HarvesterResponse(
            status="error",
            message="Thất bại: Bạn chưa bật API Key nào trong phần Cấu hình!"
        )
    background_tasks.add_task(run_harvester_engine, request_data, active_keys)
    return HarvesterResponse(
        status="processing",
        message=f"Hệ thống đã đưa vào hàng đợi chạy nền! Quá trình sẽ sử dụng {len(active_keys)} API Key xoay vòng. Bạn có thể tắt thông báo này và làm việc khác."
    )