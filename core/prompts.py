def build_dynamic_prompt(request, current_seed):
    # Khối Vai trò & Nhiệm vụ
    prompt = f"{request.role_prompt}\n"
    prompt += f"Nhiệm vụ của bạn là sinh ra CHÍNH XÁC {request.samples} mẫu JSON.\n\n"

    # Khối Bối cảnh (Nếu có)
    if current_seed.context.strip():
        prompt += f"# BỐI CẢNH SCHEMA:\n{current_seed.context}\n\n"

    # Khối Chiến thuật phân bổ (Seed Rule)
    prompt += f"# CHIẾN THUẬT PHÂN BỔ CHO {request.samples} MẪU:\n"
    prompt += f"BẮT BUỘC tuân thủ nghiêm ngặt chiến thuật sau:\n{current_seed.rule}\n\n"

    # Khối Ràng buộc
    prompt += f"# RÀNG BUỘC NGHIÊM NGẶT:\n{request.constraints_prompt}\n\n"

    # Khối Cấu trúc JSON
    prompt += f"# ĐỊNH DẠNG ĐẦU RA:\nBẮT BUỘC trả về DUY NHẤT một mảng JSON Array có cấu trúc:\n{request.schema_definition}"

    return prompt

def build_harvester_user_prompt(seed: str) -> str:
    return f"Chủ đề / Hạt giống của bạn là: {seed}"