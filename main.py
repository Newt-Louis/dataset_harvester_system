from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.settings import settings
from schemas.payloads import HarvesterResponse

app = FastAPI(
    title="AI Dataset Harvester API",
    description="Core engine cho việc gọi đa model AI (Gemini, Groq, OpenRouter...)",
    version="1.0.0"
)

# CẤU HÌNH CORS (Bắt buộc phải có để Vue ở port 5173 có thể gọi API sang port 8000)
# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # Chỉ cho phép Vue gọi sang
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "success",
        "message": "Backend API đang hoạt động! Hãy mở http://localhost:5173 để xem giao diện UI.",
        "docs_url": "http://localhost:8000/docs"
    }


# Chuẩn bị sẵn một endpoint (đường dẫn) để sau này nhận yêu cầu từ Vue
@app.post("/api/generate", response_model=HarvesterResponse)
async def generate_dataset(request_data: dict):
    print("Dữ liệu nhận từ UI:", request_data)
    final_data, file_path = await run_harvester_engine(request_data)
    total_generated = len(final_data)
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