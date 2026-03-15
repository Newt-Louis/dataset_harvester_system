import importlib
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.settings import settings
from fastapi.staticfiles import StaticFiles
from database.database import engine, Base
from database import models

Base.metadata.create_all(bind=engine)
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