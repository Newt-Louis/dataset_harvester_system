import asyncio, json, re, os, csv
from datetime import datetime
from litellm import acompletion
from core.settings import settings
from schemas.payloads import HarvesterRequest

# Đảm bảo thư mục lưu file tồn tại
os.makedirs("downloads", exist_ok=True)

# Khởi tạo Semaphore để giới hạn số luồng gọi API cùng lúc (tránh bị block API Key)
semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)


def extract_json_from_text(text: str):
    """Hàm dọn rác: Cắt bỏ các text thừa của AI để lấy đúng mảng JSON"""
    try:
        # Xóa các block markdown ```json ... ``` nếu có
        text = re.sub(r'```(?:json)?', '', text).strip()
        # Cố gắng parse luôn
        return json.loads(text)
    except json.JSONDecodeError:
        # Nếu lỗi, dùng Regex tìm đoạn bắt đầu bằng [ và kết thúc bằng ]
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        return None


async def generate_single_seed(seed: str, request: HarvesterRequest,
                               model_name: str = "openrouter/google/gemma-2-9b-it:free"):
    """Hàm xử lý cho 1 hạt giống duy nhất"""
    async with semaphore:
        print(f"🔄 Đang xử lý hạt giống: {seed[:30]}...")

        # 1. Trộn Prompt System + Lệnh ép buộc xuất JSON
        system_content = f"""{request.prompt}

        BẮT BUỘC: Bạn phải sinh ra ĐÚNG {request.samples} mẫu (samples) cho chủ đề/hạt giống được cung cấp.
        BẮT BUỘC: Trả về DUY NHẤT một mảng JSON (JSON Array), KHÔNG in thêm bất kỳ văn bản giải thích nào.

        Cấu trúc mỗi object trong mảng phải TUYỆT ĐỐI tuân theo Schema sau:
        {request.schema_definition}
        """

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Chủ đề / Hạt giống của bạn là: {seed}"}
        ]

        try:
            # 2. Gọi API bất đồng bộ (LiteLLM tự động dùng API Key trong file .env)
            response = await acompletion(
                model=model_name,
                messages=messages,
                temperature=0.7,
            )

            # 3. Lấy kết quả và dọn rác
            raw_text = response.choices[0].message.content
            parsed_data = extract_json_from_text(raw_text)

            if parsed_data and isinstance(parsed_data, list):
                print(f"✅ Thành công: {seed[:20]}... ({len(parsed_data)} mẫu)")
                return parsed_data
            else:
                print(f"❌ Lỗi Format từ AI cho seed: {seed[:20]}")
                return []

        except Exception as e:
            print(f"❌ Lỗi kết nối/API cho seed {seed[:20]}: {str(e)}")
            return []


def save_to_file(all_data: list, format_type: str):
    """Hàm lưu dữ liệu ra file"""
    if not all_data:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"downloads/dataset_{timestamp}.{format_type}"

    if format_type == "jsonl":
        with open(file_path, "w", encoding="utf-8") as f:
            for item in all_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    elif format_type == "csv":
        # Tự động lấy các keys của object đầu tiên làm tiêu đề cột
        keys = all_data[0].keys()
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(all_data)

    return file_path


async def run_harvester_engine(request: HarvesterRequest):
    """Hàm tổng phối (Orchestrator): Chạy đồng thời tất cả các seeds"""

    # Tạo danh sách các công việc (Tasks)
    flattened_data = []

    # Ở đây tôi đang hardcode model miễn phí của Google qua OpenRouter để test
    # Sau này ta có thể làm tính năng xoay tua model ở đây
    target_model = "openrouter/google/gemma-2-9b-it:free"

    for idx, seed in enumerate(request.seeds):
        res = await generate_single_seed(seed, request, target_model)
        if res:
            flattened_data.extend(res)
        if idx < len(request.seeds) - 1:
            await asyncio.sleep(3)

    # Lưu ra file
    file_path = save_to_file(flattened_data, request.format)

    return flattened_data, file_path