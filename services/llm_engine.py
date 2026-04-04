import asyncio, json, re, os, csv, traceback
from datetime import datetime
from litellm import acompletion
from litellm.exceptions import AuthenticationError, RateLimitError, ContextWindowExceededError
import database.models as models
from api.logs import write_system_log
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
    """Hàm dọn rác mạnh mẽ: Trích xuất mảng JSON kể cả khi bị lẫn văn bản hoặc bị cắt cụt nhẹ"""
    if not text:
        return None
    
    try:
        # 1. Làm sạch các ký tự điều khiển lạ
        text = text.strip()
        
        # 2. Tìm mảng JSON bằng Regex (Tìm từ dấu [ đầu tiên đến dấu ] cuối cùng)
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # 3. Nếu lỗi, thử "vá" nếu AI cắt cụt (thường thiếu ])
                if not json_str.endswith(']'):
                    try:
                        return json.loads(json_str + ']')
                    except: pass
                
                # 4. Thử phương án cuối: Tìm tất cả các object {} bên trong và ghép lại thành mảng
                try:
                    objects = re.findall(r'\{.*?\}', json_str, re.DOTALL)
                    parsed_objects = [json.loads(obj) for obj in objects]
                    if parsed_objects:
                        return parsed_objects
                except: pass
        
        # 5. Backup: Nếu không thấy [], thử tìm {} đầu tiên và cuối cùng
        match_obj = re.search(r'\{.*\}', text, re.DOTALL)
        if match_obj:
            try:
                data = json.loads(match_obj.group(0))
                return [data] if isinstance(data, dict) else data
            except: pass

        return None
    except Exception as e:
        print(f"DEBUG: Lỗi extract JSON: {e}")
        return None


async def run_harvester_engine(job_id: int, request: HarvesterRequest, user_id: int):
    """Hàm chạy nền: Lấy Key từ DB, xoay vòng API, cập nhật tiến độ"""

    db = SessionLocal()
    tracker = JobTracker(db, job_id)

    try:
        # Đảm bảo thư mục lưu file tồn tại (Dùng folder chung 'downloads')
        os.makedirs("downloads", exist_ok=True)

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
            db.refresh(tracker.job)
            if tracker.job.status == "stopped":
                tracker.add_log("Dừng chương trình theo yêu cầu.")
                break

            # --- KIỂM TRA TẤT CẢ MODEL CẠN KIỆT (Task 2) ---
            if len(working_keys) == 0:
                msg = f"Tất cả API Key ({len(active_configs)}) đều đạt giới hạn hoặc lỗi. Dừng tại hạt giống #{seed_idx + 1}."
                tracker.mark_failed(msg)
                write_system_log(db, "WARNING", f"Engine - Job {job_id}", msg)
                break

            # Cập nhật thông tin hạt giống hiện tại lên UI
            tracker.update_seed_info(seed_idx + 1, current_seed.context, current_seed.rule)
            tracker.add_log(f"Đang xử lý hạt giống {seed_idx + 1}/{len(request.seeds)}")

            seed_success = False
            keys_tried_for_this_seed = 0
            current_prompt = build_dynamic_prompt(request, current_seed)

            while not seed_success and keys_tried_for_this_seed < len(working_keys):
                db.refresh(tracker.job)
                if tracker.job.status == "stopped":
                    break

                # Đảm bảo index không vượt quá mảng
                current_key_idx = current_key_idx % len(working_keys)
                config = working_keys[current_key_idx]
                
                real_api_key = decrypt_api_key(config.api_key)
                tracker.update_provider(config.provider)
                tracker.update_model(config.model_name)

                try:
                    tracker.add_log(f"Đang gọi {config.provider} ({config.model_name})...")
                    async with semaphore:
                        response = await acompletion(
                            model=config.model_name,
                            messages=[{"role": "user", "content": current_prompt}],
                            api_key=real_api_key,
                            temperature=0.7,
                            timeout=120,
                            max_tokens=8192
                        )

                    raw_text = response.choices[0].message.content
                    parsed_data = extract_json_from_text(raw_text)

                    if parsed_data and isinstance(parsed_data, list):
                        StorageManager.append_to_local_file(job_id, parsed_data, request.format)
                        
                        tracker.add_progress(len(parsed_data))
                        total_generated_samples += len(parsed_data)
                        seed_success = True
                        keys_tried_for_this_seed = 0
                        
                        # XOAY VÒNG KEY
                        current_key_idx = (current_key_idx + 1) % len(working_keys)
                        
                        # SỬ DỤNG DELAY TÙY CHỈNH (Task 3)
                        await asyncio.sleep(request.delay) 
                    else:
                        raise Exception("AI trả về sai định dạng JSON.")

                except (AuthenticationError, RateLimitError) as e:
                    error_msg = str(e).lower()
                    if "limit" in error_msg or "auth" in error_msg or "key" in error_msg:
                         tracker.add_log(f"Model {config.model_name} bị loại bỏ (Hết hạn/Lỗi Auth).")
                         working_keys.pop(current_key_idx)
                    else:
                         keys_tried_for_this_seed += 1
                         current_key_idx = (current_key_idx + 1) % len(working_keys)
                         await asyncio.sleep(5)
                except Exception as e:
                    tracker.add_log(f"Lỗi kết nối model {config.model_name}. Thử model khác...")
                    keys_tried_for_this_seed += 1
                    current_key_idx = (current_key_idx + 1) % len(working_keys)
                    await asyncio.sleep(2)

        # --- CẬP NHẬT STATE & CẮT SEED (Task 1) ---
        state = db.query(models.HarvesterState).filter(models.HarvesterState.user_id == user_id).first()
        if state and state.seeds:
            try:
                original_seeds = json.loads(state.seeds)
                
                if tracker.job.status == "completed":
                    # Xong hết sạch -> Clear mảng
                    state.seeds = "[]"
                else:
                    # Bị dừng/lỗi -> Cắt bỏ những hạt giống ĐÃ xử lý xong hoàn toàn
                    # tracker.job.current_seed_index là 1-based index
                    # Ví dụ đang chạy hạt giống thứ 3 (index 2) mà bị dừng, 
                    # ta muốn giữ từ index 2 trở đi.
                    new_seeds = original_seeds[tracker.job.current_seed_index - 1:]
                    state.seeds = json.dumps(new_seeds, ensure_ascii=False)
                
                db.commit()
                tracker.add_log("Đã cập nhật danh sách hạt giống còn lại.")
            except Exception as se:
                write_system_log(db, "ERROR", "Engine - Seed Cutting", f"Không thể cắt tỉa hạt giống: {str(se)}")

        # Xong việc hoặc bị dừng (Stop) -> Chốt sổ
        if total_generated_samples > 0:
            StorageManager.finalize_dataset(tracker, request.format)
            if tracker.job.status not in ["completed", "stopped"]:
                tracker.job.status = "completed"
            db.commit()
        else:
            if tracker.job.status != "stopped":
                tracker.mark_failed("Quá trình chạy hoàn tất nhưng không sinh được dữ liệu hợp lệ nào.")

    except Exception as e:
        error_detail = traceback.format_exc()
        write_system_log(db, "CRITICAL", f"Engine - Job {job_id}", f"Job bị crash hoàn toàn:\n{error_detail}")
        tracker.mark_failed(str(e))
    finally:
        db.close()
