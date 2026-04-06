import asyncio, json, re, os, csv
from fastapi import HTTPException
from litellm import acompletion
from litellm.exceptions import AuthenticationError, RateLimitError, ContextWindowExceededError
from core.settings import settings
from core.security import decrypt_api_key
from schemas.payloads import TestModelRequest
from utils.normalize import extract_json_from_text

async def run_model_test(model_name: str, api_key: str, payload: TestModelRequest):
    full_prompt = f"""
    {payload.role_prompt}

    Ràng buộc nghiêm ngặt:
    {payload.constraints_prompt}

    Cấu trúc JSON mong muốn:
    {payload.schema_definition}

    Bối cảnh: {payload.seed.context}
    Quy tắc dữ liệu: {payload.seed.rule}

    BẮT BUỘC TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON. KHÔNG GIẢI THÍCH HAY VIẾT THÊM BẤT CỨ VĂN BẢN NÀO KHÁC.
    """

    try:
        response = await acompletion(
            model=model_name,
            messages=[{"role": "user", "content": full_prompt}],
            api_key=api_key,
            temperature=0.7,
            timeout=30
        )

        raw_text = response.choices[0].message.content
        parsed_data = extract_json_from_text(raw_text)

        if parsed_data is not None:
            return parsed_data
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Model phản hồi nhưng sai định dạng JSON.\n\nRaw response:\n{raw_text}"
            )

    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"Lỗi Xác thực (API Key không hợp lệ hoặc đã bị khóa):\n{str(e)}")

    except RateLimitError as e:
        raise HTTPException(status_code=429,
                            detail=f"Lỗi giới hạn (Hết quota, thiếu Credit hoặc gọi quá nhanh):\n{str(e)}")

    except ContextWindowExceededError as e:
        raise HTTPException(status_code=400, detail=f"Lỗi Context Window (Prompt quá dài):\n{str(e)}")

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi Hệ thống khi gọi AI:\n{str(e)}")