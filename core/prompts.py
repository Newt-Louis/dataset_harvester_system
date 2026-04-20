import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from litellm import get_supported_openai_params, supports_response_schema


class PromptEngine:
    ALLOWED_TYPE_KEYWORDS = {
        "string",
        "number",
        "integer",
        "float",
        "boolean",
        "date",
        "datetime",
        "array",
        "object",
        "null",
    }

    WRAPPER_KEYS = ("data", "items", "rows", "results", "records")

    @classmethod
    def validate_schema_definition(cls, schema_definition: str) -> dict:
        """
        schema_definition phải là đúng 1 object JSON mẫu.
        Ví dụ hợp lệ:
        {
          "system": "string",
          "user": "string",
          "assistant": "string"
        }

        Hỗ trợ thêm:
        - nested object: {"meta": {"score": "number"}}
        - array 1 phần tử mẫu: {"tags": ["string"]}
        - object shorthand: {"payload": "object"}
        - array shorthand: {"items": "array"}
        """
        if not schema_definition or not schema_definition.strip():
            raise ValueError("schema_definition không được để trống.")

        try:
            parsed = json.loads(schema_definition)
        except json.JSONDecodeError as e:
            raise ValueError(f"schema_definition không phải JSON hợp lệ: {e}")

        if not isinstance(parsed, dict):
            raise ValueError("schema_definition phải là đúng 1 object JSON mẫu, không được là array hoặc primitive.")

        if not parsed:
            raise ValueError("schema_definition không được là object rỗng.")

        cls._validate_schema_node(parsed, path="$", is_root=True)
        return parsed

    @classmethod
    def _validate_schema_node(cls, node: Any, path: str, is_root: bool = False) -> None:
        if isinstance(node, dict):
            if not node and is_root:
                raise ValueError("Object gốc của schema_definition không được rỗng.")

            for key, value in node.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(f"Khóa tại {path} phải là string không rỗng.")
                cls._validate_schema_node(value, f"{path}.{key}")
            return

        if isinstance(node, list):
            if len(node) != 1:
                raise ValueError(
                    f"Mảng schema tại {path} phải chứa đúng 1 phần tử mẫu, ví dụ ['string'] hoặc [{{...}}]."
                )
            cls._validate_schema_node(node[0], f"{path}[0]")
            return

        if isinstance(node, str):
            keyword = node.strip().lower()
            if keyword not in cls.ALLOWED_TYPE_KEYWORDS:
                allowed = ", ".join(sorted(cls.ALLOWED_TYPE_KEYWORDS))
                raise ValueError(
                    f"Kiểu dữ liệu không hợp lệ tại {path}: '{node}'. "
                    f"Chỉ chấp nhận: {allowed}."
                )
            return

        raise ValueError(
            f"Giá trị tại {path} không hợp lệ. "
            "Mỗi thuộc tính chỉ được là: string keyword, object lồng nhau, hoặc array 1 phần tử mẫu."
        )

    @classmethod
    def normalize_schema_definition(cls, schema_definition: str) -> str:
        parsed = cls.validate_schema_definition(schema_definition)
        return json.dumps(parsed, ensure_ascii=False, indent=2)

    @classmethod
    def supports_native_structured_output(cls, provider: str, model_name: str) -> bool:
        provider = (provider or "").strip().lower()

        # Cố gắng theo model name trực tiếp trước
        try:
            params = get_supported_openai_params(model=model_name)
            if "response_format" in params and supports_response_schema(model=model_name):
                return True
        except Exception:
            pass

        # Fallback theo provider
        try:
            params = get_supported_openai_params(
                model=model_name,
                custom_llm_provider=provider if provider else None,
            )
            if "response_format" in params and supports_response_schema(
                model=model_name,
                custom_llm_provider=provider if provider else None,
            ):
                return True
        except Exception:
            pass

        return False

    @classmethod
    def build_native_response_format(cls, schema_definition: str, samples: int) -> dict:
        schema_object = cls.validate_schema_definition(schema_definition)
        item_schema = cls._build_json_schema_from_template(schema_object)

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "dataset_rows",
                "strict": True,
                "schema": {
                    "type": "array",
                    "minItems": samples,
                    "maxItems": samples,
                    "items": item_schema,
                },
            },
        }

    @classmethod
    def _build_json_schema_from_template(cls, node: Any) -> dict:
        if isinstance(node, dict):
            properties = {}
            required = []
            for key, value in node.items():
                properties[key] = cls._build_json_schema_from_template(value)
                required.append(key)

            return {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            }

        if isinstance(node, list):
            return {
                "type": "array",
                "items": cls._build_json_schema_from_template(node[0]),
            }

        if isinstance(node, str):
            keyword = node.strip().lower()

            if keyword == "string":
                return {"type": "string"}
            if keyword == "number":
                return {"type": "number"}
            if keyword == "float":
                return {"type": "number"}
            if keyword == "integer":
                return {"type": "integer"}
            if keyword == "boolean":
                return {"type": "boolean"}
            if keyword == "date":
                return {"type": "string", "format": "date"}
            if keyword == "datetime":
                return {"type": "string", "format": "date-time"}
            if keyword == "null":
                return {"type": "null"}
            if keyword == "array":
                return {"type": "array", "items": {"type": "string"}}
            if keyword == "object":
                return {"type": "object", "additionalProperties": True}

        return {"type": "string"}

    @classmethod
    def build_prompt_contract(cls, schema_definition: str, samples: int, native_structured_output: bool) -> str:
        normalized_schema = cls.normalize_schema_definition(schema_definition)

        contract = [
            "# ĐỊNH DẠNG ĐẦU RA BẮT BUỘC:",
            f"- Trả về DUY NHẤT 1 JSON Array gồm đúng {samples} phần tử.",
            "- Mỗi phần tử trong array là 1 object theo đúng schema bên dưới.",
            "- Không được trả về markdown, không code fence, không giải thích, không văn bản thừa.",
            "- Không được thiếu khóa, không được thêm khóa ngoài schema.",
            "- Chỉ trả về JSON hợp lệ.",
            "",
            "# SCHEMA CỦA 1 OBJECT MẪU:",
            normalized_schema,
        ]

        if native_structured_output:
            contract.insert(
                1,
                "- Hệ thống đang ép schema bằng native structured output; nội dung vẫn phải khớp đúng kiểu dữ liệu.",
            )
        else:
            contract.insert(
                1,
                "- Model này không hỗ trợ ép schema native; bạn phải tuân thủ tuyệt đối định dạng bằng chính nội dung trả lời.",
            )

        return "\n".join(contract)

    @classmethod
    def build_dynamic_prompt(cls, request, current_seed, native_structured_output: bool = False) -> str:
        prompt = f"{request.role_prompt}\n"
        prompt += f"Nhiệm vụ của bạn là sinh ra CHÍNH XÁC {request.samples} mẫu JSON.\n\n"

        if current_seed.context.strip():
            prompt += f"# BỐI CẢNH SCHEMA:\n{current_seed.context}\n\n"

        prompt += f"# CHIẾN THUẬT PHÂN BỔ CHO {request.samples} MẪU:\n"
        prompt += f"BẮT BUỘC tuân thủ nghiêm ngặt chiến thuật sau:\n{current_seed.rule}\n\n"

        prompt += f"# RÀNG BUỘC NGHIÊM NGẶT:\n{request.constraints_prompt}\n\n"
        prompt += cls.build_prompt_contract(
            schema_definition=request.schema_definition,
            samples=request.samples,
            native_structured_output=native_structured_output,
        )

        return prompt

    @classmethod
    def build_acompletion_kwargs(
        cls,
        provider: str,
        model_name: str,
        api_key: str,
        prompt: str,
        schema_definition: str,
        samples: int,
        timeout: int = 600,
        max_tokens: int = 8192,
        temperature: float = 0.8,
    ) -> Tuple[dict, bool]:
        native_structured_output = cls.supports_native_structured_output(provider, model_name)

        call_kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "api_key": api_key,
            "timeout": timeout,
            "max_tokens": max_tokens,
        }

        # Giữ đúng logic cũ của bạn: GPT-5 không set temperature
        if "gpt-5" not in model_name.lower():
            call_kwargs["temperature"] = temperature

        if native_structured_output:
            call_kwargs["response_format"] = cls.build_native_response_format(
                schema_definition=schema_definition,
                samples=samples,
            )

        return call_kwargs, native_structured_output

    @classmethod
    def build_generation_plan(
        cls,
        request,
        current_seed,
        provider: str,
        model_name: str,
        api_key: str,
        timeout: int = 600,
        max_tokens: int = 8192,
        temperature: float = 0.8,
    ) -> dict:
        native_structured_output = cls.supports_native_structured_output(provider, model_name)
        prompt = cls.build_dynamic_prompt(
            request=request,
            current_seed=current_seed,
            native_structured_output=native_structured_output,
        )
        call_kwargs, _ = cls.build_acompletion_kwargs(
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            prompt=prompt,
            schema_definition=request.schema_definition,
            samples=request.samples,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return {
            "prompt": prompt,
            "call_kwargs": call_kwargs,
            "native_structured_output": native_structured_output,
        }

    @classmethod
    def extract_response_text(cls, response) -> str:
        if not getattr(response, "choices", None):
            return ""

        message = response.choices[0].message
        content = getattr(message, "content", "")

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
                else:
                    text_value = getattr(item, "text", None)
                    if isinstance(text_value, str):
                        parts.append(text_value)
            return "".join(parts).strip()

        return ""

    @classmethod
    def extract_json_from_text(cls, text: str):
        if not text:
            return None

        text = text.strip()

        # parse toàn bộ text
        try:
            parsed = json.loads(text)
            return cls._unwrap_dataset(parsed)
        except Exception:
            pass

        # parse code block json
        code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
        for block in reversed(code_blocks):
            try:
                parsed = json.loads(block.strip())
                result = cls._unwrap_dataset(parsed)
                if result is not None:
                    return result
            except Exception:
                pass

        # quét raw JSON value đầu tiên giải mã được
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[idx:])
                result = cls._unwrap_dataset(parsed)
                if result is not None:
                    return result
            except Exception:
                continue

        return None

    @classmethod
    def _unwrap_dataset(cls, parsed: Any):
        if isinstance(parsed, list):
            return parsed

        if isinstance(parsed, dict):
            for key in cls.WRAPPER_KEYS:
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            return [parsed]

        return None

    @classmethod
    def parse_and_validate_dataset(cls, response, schema_definition: str) -> List[dict]:
        raw_text = cls.extract_response_text(response)
        if not raw_text:
            raise ValueError("AI không trả về nội dung text hợp lệ để trích xuất JSON.")

        parsed_data = cls.extract_json_from_text(raw_text)
        if parsed_data is None:
            raise ValueError("AI không trả về JSON hợp lệ.")

        schema_object = cls.validate_schema_definition(schema_definition)
        return cls.validate_dataset_against_schema(
            data=parsed_data,
            schema_object=schema_object
        )

    @classmethod
    def validate_dataset_against_schema(cls, data: Any, schema_object: dict) -> List[dict]:
        if not isinstance(data, list):
            raise ValueError("Output phải là một JSON Array.")

        validated = []
        for idx, item in enumerate(data):
            cls._validate_value_against_template(
                value=item,
                template=schema_object,
                path=f"$[{idx}]",
            )
            validated.append(item)

        return validated

    @classmethod
    def _validate_value_against_template(cls, value: Any, template: Any, path: str) -> None:
        if isinstance(template, dict):
            if not isinstance(value, dict):
                raise ValueError(f"{path} phải là object.")

            expected_keys = set(template.keys())
            actual_keys = set(value.keys())

            missing = expected_keys - actual_keys
            extra = actual_keys - expected_keys

            if missing:
                raise ValueError(f"{path} bị thiếu khóa: {', '.join(sorted(missing))}.")
            if extra:
                raise ValueError(f"{path} có khóa dư: {', '.join(sorted(extra))}.")

            for key, child_template in template.items():
                cls._validate_value_against_template(
                    value=value[key],
                    template=child_template,
                    path=f"{path}.{key}",
                )
            return

        if isinstance(template, list):
            if not isinstance(value, list):
                raise ValueError(f"{path} phải là array.")

            item_template = template[0]
            for idx, item in enumerate(value):
                cls._validate_value_against_template(
                    value=item,
                    template=item_template,
                    path=f"{path}[{idx}]",
                )
            return

        if not isinstance(template, str):
            raise ValueError(f"Schema nội bộ tại {path} không hợp lệ.")

        keyword = template.strip().lower()

        if keyword == "string":
            if not isinstance(value, str):
                raise ValueError(f"{path} phải là string.")
            return

        if keyword in ("number", "float"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{path} phải là number.")
            return

        if keyword == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{path} phải là integer.")
            return

        if keyword == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{path} phải là boolean.")
            return

        if keyword == "null":
            if value is not None:
                raise ValueError(f"{path} phải là null.")
            return

        if keyword == "array":
            if not isinstance(value, list):
                raise ValueError(f"{path} phải là array.")
            return

        if keyword == "object":
            if not isinstance(value, dict):
                raise ValueError(f"{path} phải là object.")
            return

        if keyword == "date":
            if not isinstance(value, str):
                raise ValueError(f"{path} phải là date string.")
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError(f"{path} phải có định dạng date ISO yyyy-mm-dd.")
            return

        if keyword == "datetime":
            if not isinstance(value, str):
                raise ValueError(f"{path} phải là datetime string.")
            candidate = value.replace("Z", "+00:00")
            try:
                datetime.fromisoformat(candidate)
            except ValueError:
                raise ValueError(f"{path} phải có định dạng datetime ISO hợp lệ.")
            return

        raise ValueError(f"{path} có keyword type không được hỗ trợ: {template}")


def build_dynamic_prompt(request, current_seed):
    return PromptEngine.build_dynamic_prompt(request, current_seed, native_structured_output=False)


def build_harvester_user_prompt(seed: str) -> str:
    return f"Chủ đề / Hạt giống của bạn là: {seed}"