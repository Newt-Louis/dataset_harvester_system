import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

class Settings:
    _raw_cors = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    CORS_ORIGINS: List[str] = [origin.strip() for origin in _raw_cors.split(",")]
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")

    MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", 5))
    TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", 60))

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "sqlite:///./database/dataset_harvester.db"
    )
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-for-local-dev-only")
    FERNET_KEY = os.getenv("FERNET_KEY", "uE2d3_z6iW-N2U9D8fC6mQ5J8sP0kX2yZ1bH7vN3M4=")

    # S3 (AWS, Cloudflare R2, Supabase...)
    S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
    S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
    S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
    S3_PUBLIC_URL = os.getenv("S3_PUBLIC_URL", "")

    ADMIN_EMAILS: str = os.getenv("ADMIN_EMAILS", "admin@localhost.com")
settings = Settings()