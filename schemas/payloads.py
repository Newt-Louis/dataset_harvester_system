from pydantic import BaseModel, Field
from typing import List, Optional

class APIConfig(BaseModel):
    provider: str
    apiKey: str
    modelName: str
    isActive: bool = True

class ConfigCreate(BaseModel):
    provider: str
    api_key: str
    model_name: str

class ConfigResponse(BaseModel):
    id: int
    provider: str
    model_name: str
    is_active: bool

    class Config:
        from_attributes = True

class ConfigResponseWithKey(ConfigResponse):
    api_key_masked: str

class SeedItem(BaseModel):
    """Một phần tử hạt giống bao gồm Bối cảnh và Chiến thuật tương ứng"""
    context: str = Field(default="", description="Bối cảnh Schema (có thể để trống)")
    rule: str = Field(..., description="Chiến thuật phân bổ (Bắt buộc)")

class HarvesterRequest(BaseModel):
    role_prompt: str = Field(..., description="Vai trò của AI")
    constraints_prompt: str = Field(..., description="Ràng buộc nghiêm ngặt")
    schema_definition: str = Field(..., description="Cấu trúc JSON mong muốn dạng chuỗi")
    seeds: List[SeedItem] = Field(..., description="Danh sách các cặp Bối cảnh & Quy tắc")
    format: str = Field(..., description="Định dạng đầu ra: jsonl hoặc csv")
    samples: int = Field(..., description="Số lượng mẫu trên mỗi hạt giống")
    delay: int = Field(default=2, description="Thời gian nghỉ giữa các request (giây)")

class HarvesterResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[int] = None

class TestSeedItem(BaseModel):
    context: str
    rule: str

class TestModelRequest(BaseModel):
    role_prompt: str
    constraints_prompt: str
    schema_definition: str
    seed: TestSeedItem