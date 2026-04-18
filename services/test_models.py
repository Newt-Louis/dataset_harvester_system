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
        # Fix lỗi openai từ phiên bản gpt-5 không nhận tham số temperature nữa !!
        call_kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": full_prompt}],
            "api_key": api_key,
            "timeout": 600,
            "max_tokens": 8192,
        }

        if "gpt-5" not in model_name:
            call_kwargs["temperature"] = 0.8
        elif "gpt-5.1" in model_name:
            call_kwargs["max_tokens"] = 65536
            pass

        response = await acompletion(**call_kwargs)
        print(response)
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
        raise HTTPException(status_code=400, detail=f"Lỗi Xác thực (API Key không hợp lệ hoặc đã bị khóa):\n{str(e)}")

    except RateLimitError as e:
        raise HTTPException(status_code=429,
                            detail=f"Lỗi giới hạn (Hết quota, thiếu Credit hoặc gọi quá nhanh):\n{str(e)}")

    except ContextWindowExceededError as e:
        raise HTTPException(status_code=400, detail=f"Lỗi Context Window (Prompt quá dài):\n{str(e)}")

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi Hệ thống khi gọi AI:\n{str(e)}")