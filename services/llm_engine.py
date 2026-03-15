import asyncio, json, re, os, csv
from datetime import datetime
from litellm import acompletion

from core.settings import settings
from core.prompts import build_harvester_system_prompt, build_harvester_user_prompt
from core.security import decrypt_api_key
from database.database import SessionLocal
from database.models import ApiConfig
from services.job_tracker import JobTracker
from schemas.payloads import HarvesterRequest

# Đảm bảo thư mục lưu file tồn tại
os.makedirs("downloads", exist_ok=True)

# Khởi tạo Semaphore để giới hạn số luồng gọi API cùng lúc (tránh bị block API Key)
semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)


def extract_json_from_text(text: str):
    """Hàm dọn rác: Cắt bỏ các text thừa của AI để lấy đúng mảng JSON"""
    try:
        text = re.sub(r'```(?:json)?', '', text).strip()
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        return None


def save_to_file(all_data: list, format_type: str):
    # (Giữ nguyên logic ghi file cũ của bạn)
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
    return file_path


async def run_harvester_engine(job_id: int, request: HarvesterRequest, user_id: int):
    """Hàm chạy nền: Lấy Key từ DB, xoay vòng API, cập nhật tiến độ"""

    # 1. Tự mở một phiên làm việc Database MỚI cho Background Task
    db = SessionLocal()
    tracker = JobTracker(db, job_id)

    try:
        # Lấy danh sách API Key đang Active của User này
        active_configs = db.query(ApiConfig).filter(
            ApiConfig.user_id == user_id,
            ApiConfig.is_active == True
        ).all()

        if not active_configs:
            raise Exception("Bạn chưa có cấu hình API Key nào đang hoạt động.")

        flattened_data = []
        current_key_idx = 0

        tracker.job.status = "running"
        db.commit()

        # Chuẩn bị System Prompt
        system_content = build_harvester_system_prompt(request.prompt, request.samples, request.schema_definition)

        for seed in request.seeds:
            seed_success = False
            attempts = 0

            while not seed_success and attempts < len(active_configs):
                config = active_configs[current_key_idx]

                # Giải mã API Key bằng Fernet
                real_api_key = decrypt_api_key(config.api_key)
                tracker.update_model(config.model_name)

                print(f"🔄 Đang xử lý hạt giống: {seed[:20]}... (Model: {config.model_name})")

                try:
                    async with semaphore:
                        response = await acompletion(
                            model=config.model_name,
                            messages=[
                                {"role": "system", "content": system_content},
                                {"role": "user", "content": build_harvester_user_prompt(seed)}
                            ],
                            api_key=real_api_key,  # Bơm Key thật đã giải mã vào đây
                            temperature=0.7,
                        )

                    raw_text = response.choices[0].message.content
                    parsed_data = extract_json_from_text(raw_text)

                    if parsed_data and isinstance(parsed_data, list):
                        flattened_data.extend(parsed_data)
                        tracker.add_progress(len(parsed_data))  # Báo cáo Dashboard
                        seed_success = True
                        await asyncio.sleep(2)  # Nghỉ để tránh Rate Limit
                    else:
                        raise Exception("AI trả về sai định dạng JSON.")

                except Exception as e:
                    print(f"❌ Lỗi Model {config.model_name}: {str(e)}")
                    current_key_idx = (current_key_idx + 1) % len(active_configs)
                    attempts += 1
                    await asyncio.sleep(1)

            if not seed_success:
                print(f"💀 BỎ QUA HẠT GIỐNG: {seed[:20]}")

        # Xong việc -> Lưu file
        if flattened_data:
            file_path = save_to_file(flattened_data, request.format)
            download_url = f"http://localhost:8000/{file_path}"
            tracker.mark_completed(download_url)
        else:
            tracker.mark_failed("Quá trình chạy hoàn tất nhưng không sinh được dữ liệu hợp lệ nào.")

    except Exception as e:
        tracker.mark_failed(str(e))
    finally:
        db.close()  # RẤT QUAN TRỌNG: Làm xong phải dọn dẹp kết nối Database