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

settings = Settings()