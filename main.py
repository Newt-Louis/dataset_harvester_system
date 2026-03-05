from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.settings import settings
from api import home,harvesting

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

app.include_router(home.router, tags=["Home"])
app.include_router(harvesting.router, prefix="/api", tags=["Harvesting"])