from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI Dataset Harvester API",
    description="Core engine cho việc gọi đa model AI (Gemini, Groq, OpenRouter...)",
    version="1.0.0"
)

# CẤU HÌNH CORS (Bắt buộc phải có để Vue ở port 5173 có thể gọi API sang port 8000)
# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Chỉ cho phép Vue gọi sang
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
@app.post("/api/generate")
async def generate_dataset(request_data: dict):
    print("Dữ liệu nhận từ UI:", request_data)

    return {
        "status": "processing",
        "message": "Đã nhận yêu cầu sinh dữ liệu. Đang gọi AI...",
        "received_data": request_data
    }