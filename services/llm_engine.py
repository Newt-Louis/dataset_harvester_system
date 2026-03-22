import asyncio, json, re, os, csv
from datetime import datetime
from litellm import acompletion
from litellm.exceptions import AuthenticationError, RateLimitError, ContextWindowExceededError

from core.settings import settings
from core.prompts import build_dynamic_prompt
from core.security import decrypt_api_key
from database.database import SessionLocal
from database.models import ApiConfig
from services.job_tracker import JobTracker
from schemas.payloads import HarvesterRequest
from services.storage_service import StorageManager

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

    # Tự mở một phiên làm việc Database MỚI cho Background Task
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

        working_keys = list(active_configs)
        current_key_idx = 0
        total_generated_samples = 0

        tracker.job.status = "running"
        db.commit()

        for seed_idx, current_seed in enumerate(request.seeds):
            if len(working_keys) == 0:
                error_msg = f"Hệ thống dừng sớm tại #{seed_idx + 1}: Toàn bộ API Key của bạn đã hết lượt hoặc đạt giới hạn."
                tracker.job.error_message = error_msg
                break

            seed_success = False
            keys_tried_for_this_seed = 0
            current_prompt = build_dynamic_prompt(request, current_seed)

            while not seed_success and keys_tried_for_this_seed < len(working_keys):
                config = working_keys[current_key_idx]

                # Giải mã API Key bằng Fernet
                real_api_key = decrypt_api_key(config.api_key)
                tracker.update_model(config.model_name)

                try:
                    async with semaphore:
                        response = await acompletion(
                            model=config.model_name,
                            messages=[{"role": "user", "content": current_prompt}],
                            api_key=real_api_key,  # Bơm Key thật đã giải mã vào đây
                            temperature=0.7,
                            timeout=60
                        )

                    raw_text = response.choices[0].message.content
                    parsed_data = extract_json_from_text(raw_text)

                    if parsed_data and isinstance(parsed_data, list):
                        file_path = StorageManager.append_to_local_file(job_id, parsed_data, request.format)
                        tracker.add_progress(len(parsed_data))  # Báo cáo Dashboard
                        generated_count = len(parsed_data)
                        total_generated_samples += generated_count
                        seed_success = True
                        keys_tried_for_this_seed = 0
                        await asyncio.sleep(2)  # Nghỉ để tránh Rate Limit
                    else:
                        raise Exception("AI trả về sai định dạng JSON.")

                except AuthenticationError as e:
                    working_keys.pop(current_key_idx)
                except RateLimitError as e:
                    error_msg = str(e).lower()
                    # Phân biệt Quota Ngày (RPD) vs Quá tải Phút (RPM/TPM)
                    if "limit: 0" in error_msg or "perday" in error_msg or "daily" in error_msg:
                        # Hết quota ngày, hoặc model bị cấm -> Xóa key này khỏi danh sách làm việc
                        working_keys.pop(current_key_idx)
                        # KHÔNG tăng keys_tried_for_this_seed vì mảng đã bị rút ngắn
                    else:
                        # Bị Rate limit phút -> Không xóa key, chỉ chuyển sang key khác hoặc đi ngủ
                        keys_tried_for_this_seed += 1
                        if len(working_keys) == 1:
                            # Nếu chỉ có 1 key mà bị rate limit, bắt buộc phải ngủ đông 60 giây
                            await asyncio.sleep(60)
                        else:
                            # Đổi sang key tiếp theo trong mảng
                            current_key_idx = (current_key_idx + 1) % len(working_keys)
                            await asyncio.sleep(2)
                except ContextWindowExceededError as e:
                    break
                except Exception as e:
                    keys_tried_for_this_seed += 1
                    current_key_idx = (current_key_idx + 1) % len(working_keys)
                    await asyncio.sleep(1)
                if working_keys:
                    current_key_idx = current_key_idx % len(working_keys)

            if not seed_success and working_keys:
                continue

        # Xong việc -> Lưu file
        if total_generated_samples > 0:
            StorageManager.finalize_dataset(tracker, request.format)
            if tracker.job.error_message and tracker.job.status != "completed":
                tracker.job.status = "failed"  # Đánh dấu đỏ trên UI
        else:
            tracker.mark_failed("Quá trình chạy hoàn tất nhưng không sinh được dữ liệu hợp lệ nào.")

    except Exception as e:
        tracker.mark_failed(str(e))
    finally:
        db.close()  # RẤT QUAN TRỌNG: Dọn dẹp kết nối Database