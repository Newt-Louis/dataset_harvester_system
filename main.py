import importlib
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.settings import settings
from fastapi.staticfiles import StaticFiles
import traceback
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from database.database import SessionLocal
from api.logs import write_system_log
from database.database import engine, Base
from database import models
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

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Khởi tạo kết nối DB cục bộ (ở đây không dùng Depends được)
    db = SessionLocal()
    try:
        source = f"API: {request.method} {request.url.path}"
        # Lỗi 4xx lỗi logic/người dùng -> Đánh dấu WARNING
        # Lỗi 5xx lỗi Server -> Đánh dấu ERROR
        level = "WARNING" if exc.status_code < 500 else "ERROR"

        # Ghi log tự động
        write_system_log(db, level=level, source=source, message=str(exc.detail))
    finally:
        db.close()  # Rất quan trọng: phải đóng DB

        # Trả về lỗi nguyên bản cho người dùng
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    db = SessionLocal()
    try:
        source = f"CRASH: {request.method} {request.url.path}"

        # Lấy toàn bộ dấu vết lỗi (Traceback) để biết chính xác lỗi ở dòng code nào
        error_detail = traceback.format_exc()

        # Ghi log với mức độ CRITICAL (Nguy hiểm nhất)
        write_system_log(db, level="CRITICAL", source=source, message=error_detail)
    finally:
        db.close()
    return JSONResponse(
        status_code=500,
        content={"detail": "Hệ thống gặp sự cố ngoài ý muốn. Đội ngũ kỹ thuật đã được thông báo!"},
    )

app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

def include_routers_automatically():
    api_dir = Path(__file__).parent / "api"

    for file in api_dir.glob("*.py"):
        if file.name.startswith("__"):
            continue

        # Lấy tên module (Ví dụ: từ api/home.py -> api.home)
        module_name = f"api.{file.stem}"

        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "router"):
                app.include_router(module.router)
        except Exception as e:
            print(f"⚠️ Không thể load route từ {file.name}: {e}")

include_routers_automatically()