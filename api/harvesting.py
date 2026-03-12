from fastapi import APIRouter
from schemas.payloads import HarvesterRequest, HarvesterResponse
from services.llm_engine import run_harvester_engine

router = APIRouter(prefix="/api", tags=["Harvesting"])

@router.post("/generate", response_model=HarvesterResponse)
async def generate_dataset(request_data: HarvesterRequest):
    print("Dữ liệu nhận từ UI:", request_data)
    final_data, file_path = await run_harvester_engine(request_data)
    total_generated = len(final_data) if final_data else 0
    if total_generated == 0:
        return HarvesterResponse(
            status="error",
            message="Quá trình sinh dữ liệu thất bại. Các Model AI trả về sai định dạng hoặc lỗi kết nối.",
            total_generated=0,
            file_url=""
        )
    return HarvesterResponse(
        status="success",
        message=f"Thành công! Đã sinh {total_generated} mẫu dữ liệu ra file {request_data.format.upper()}.",
        total_generated=total_generated,
        file_url=f"/{file_path}"
    )