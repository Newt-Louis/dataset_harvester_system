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
    # ... (code cũ giữ nguyên)
    if not all_data: return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"downloads/dataset_{timestamp}.{format_type}"
    if format_type == "jsonl":
        with open(file_path, "w", encoding="utf-8") as f:
            for item in all_data: f.write(json.dumps(item, ensure_ascii=False) + "\n")
    elif format_type == "csv":
        keys = all_data[0].keys()
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(all_data)
    print(f"🎉 ĐÃ LƯU FILE THÀNH CÔNG TẠI: {file_path}")
    return file_path


async def run_harvester_engine(request: HarvesterRequest, active_keys: list):
    """Hàm chạy nền: Xử lý xoay vòng API Key"""
    flattened_data = []
    current_key_idx = 0  # Bắt đầu với Key đầu tiên trong danh sách

    for seed in request.seeds:
        seed_success = False
        attempts = 0

        # Thử tối đa bằng đúng số lượng Key ta có (để tránh vòng lặp vô hạn nếu tất cả Key đều chết)
        while not seed_success and attempts < len(active_keys):
            # Lấy cấu hình Key hiện tại
            config = active_keys[current_key_idx]
            print(f"🔄 Đang xử lý hạt giống: {seed[:20]}... (Bằng model: {config.modelName})")

            system_content = f"""{request.prompt}
            BẮT BUỘC: Bạn phải sinh ra ĐÚNG {request.samples} mẫu.
            BẮT BUỘC: Trả về DUY NHẤT một mảng JSON (JSON Array), KHÔNG in thêm văn bản thừa.
            Cấu trúc JSON Schema:
            {request.schema_definition}
            """

            try:
                # GỌI API VÀ TRUYỀN KEY ĐỘNG VÀO (Không xài .env nữa)
                response = await acompletion(
                    model=config.modelName,
                    messages=[
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": f"Chủ đề / Hạt giống của bạn là: {seed}"}
                    ],
                    api_key=config.apiKey,  # Quan trọng: Bơm Key từ Vuejs vào đây
                    temperature=0.7,
                )

                raw_text = response.choices[0].message.content
                parsed_data = extract_json_from_text(raw_text)

                if parsed_data and isinstance(parsed_data, list):
                    print(f"✅ Xong hạt giống: {seed[:20]} (Đã sinh {len(parsed_data)} mẫu)")
                    flattened_data.extend(parsed_data)
                    seed_success = True

                    # Nghỉ 3s để bảo vệ Key hiện tại
                    await asyncio.sleep(3)
                else:
                    raise Exception("AI trả về sai định dạng JSON.")

            except Exception as e:
                print(f"❌ Lỗi với Key/Model ({config.modelName}): {str(e)}")
                # XOAY TUA: Chuyển sang Key tiếp theo
                current_key_idx = (current_key_idx + 1) % len(active_keys)
                attempts += 1
                print(f"🔄 Tự động chuyển đổi sang Key/Model tiếp theo...")
                await asyncio.sleep(1)  # Nghỉ 1 nhịp trước khi thử key mới

        if not seed_success:
            print(f"💀 BỎ QUA HẠT GIỐNG: {seed[:20]} (Tất cả các API Key đều thất bại)")

    # Sau khi chạy hết tất cả hạt giống, lưu file
    if flattened_data:
        save_to_file(flattened_data, request.format)
        # Ở bài sau ta sẽ thêm logic: Upload file này lên Google Drive ở ngay chỗ này!
    else:
        print("⚠️ Thu hoạch hoàn tất nhưng không có dữ liệu nào được sinh ra.")