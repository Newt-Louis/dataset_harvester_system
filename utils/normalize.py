import json, re

def mask_key(raw_key: str) -> str:
    if len(raw_key) <= 8:
        return "***"
    return raw_key[:4] + "..." + raw_key[-4:]

def extract_json_from_text(text: str):
    """Hàm dọn rác mạnh mẽ: Trích xuất mảng JSON kể cả khi bị lẫn văn bản hoặc bị cắt cụt nhẹ"""
    if not text:
        return None

    def unwrap_data(parsed):
        if isinstance(parsed, dict) and "data" in parsed and isinstance(parsed["data"], list):
            return parsed["data"]
        if isinstance(parsed, list):
            return parsed
        return None

    try:
        text = text.strip()
        code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', text)
        for block in reversed(code_blocks):
            block = block.strip()
            try:
                parsed = json.loads(block)
                result = unwrap_data(parsed)
                if result is not None:
                    return result
            except json.JSONDecodeError:
                pass

        try:
            parsed = json.loads(text)
            result = unwrap_data(parsed)
            if result is not None:
                return result
        except json.JSONDecodeError:
            pass

        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                if not json_str.endswith(']'):
                    try:
                        return json.loads(json_str + ']')
                    except:
                        pass

                try:
                    objects = re.findall(r'\{.*?\}', json_str, re.DOTALL)
                    parsed_objects = [json.loads(obj) for obj in objects]
                    if parsed_objects:
                        return parsed_objects
                except:
                    pass

        match_obj = re.search(r'\{.*\}', text, re.DOTALL)
        if match_obj:
            try:
                data = json.loads(match_obj.group(0))
                result = unwrap_data(data)
                if result is not None:
                    return result
                return [data] if isinstance(data, dict) else data
            except:
                pass

        return None
    except Exception as e:
        print(f"DEBUG: Lỗi extract JSON: {e}")
        return None