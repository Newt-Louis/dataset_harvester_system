# backend/core/prompts.py

def build_harvester_system_prompt(base_prompt: str, samples: int, schema_def: str) -> str:
    """Tạo System Prompt ép AI trả về chuẩn JSON Array"""
    return f"""{base_prompt}

    BẮT BUỘC: Bạn phải sinh ra ĐÚNG {samples} mẫu (samples) cho chủ đề/hạt giống được cung cấp.
    BẮT BUỘC: Trả về DUY NHẤT một mảng JSON (JSON Array), KHÔNG in thêm bất kỳ văn bản giải thích nào.

    Cấu trúc mỗi object trong mảng phải TUYỆT ĐỐI tuân theo Schema sau:
    {schema_def}
    """

def build_harvester_user_prompt(seed: str) -> str:
    return f"Chủ đề / Hạt giống của bạn là: {seed}"