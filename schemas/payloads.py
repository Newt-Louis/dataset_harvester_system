from pydantic import BaseModel, Field
from typing import List

class APIConfig(BaseModel):
    provider: str
    apiKey: str
    modelName: str
    isActive: bool = True

class HarvesterRequest(BaseModel):
    prompt: str = Field(..., description="Yêu cầu hệ thống và vai trò (System Prompt)")
    seeds: List[str] = Field(..., description="Danh sách hạt giống")
    schema_definition: str = Field(..., alias="schema", description="Cấu trúc JSON mong muốn dạng chuỗi")
    format: str = Field(..., description="Định dạng đầu ra: jsonl hoặc csv")
    samples: int = Field(..., description="Số lượng mẫu trên mỗi hạt giống")

class HarvesterResponse(BaseModel):
    status: str
    message: str
    total_generated: int
    file_url: str = None