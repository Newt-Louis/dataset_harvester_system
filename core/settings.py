import os
from dotenv import load_dotenv
from typing import List

from pydantic import field_validator

load_dotenv()

class Settings:
    CORS_ORIGINS: List[str] = []
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")

    MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", 5))
    TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", 60))

    @field_validator("CORS_ORIGINS",mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",")]
        return value

settings = Settings()