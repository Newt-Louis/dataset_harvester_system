import json
from sqlalchemy.orm import Session
from database.models import HarvestJob
from datetime import datetime

class JobTracker:
    def __init__(self, db: Session, job_id: int):
        self.db = db
        self.job_id = job_id
        self.job = self.db.query(HarvestJob).get(job_id)

    def update_seed_info(self, index: int, context: str, rule: str):
        """Cập nhật thông tin hạt giống hiện tại lên Dashboard"""
        self.job.current_seed_index = index
        self.job.current_seed_context = context
        self.job.current_seed_rule = rule
        self.db.commit()

    def update_provider(self, provider_name: str):
        """Cập nhật provider đang gọi AI"""
        if self.job.current_provider != provider_name:
            self.job.current_provider = provider_name
            self.db.commit()

    def update_model(self, model_name: str):
        if self.job.current_model != model_name:
            self.job.current_model = model_name
            self.db.commit()

    def add_progress(self, new_samples: int):
        self.job.samples_generated += new_samples
        self.db.commit()

    def add_log(self, message: str):
        """Lưu log ngắn gọn vào bảng harvest_jobs để hiện lên Dashboard"""
        try:
            logs = json.loads(self.job.log_messages or "[]")
            new_log = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "msg": message
            }
            logs.append(new_log)
            # Giữ tối đa 50 log mới nhất để không nặng DB
            self.job.log_messages = json.dumps(logs[-50:], ensure_ascii=False)
            self.db.commit()
        except:
            pass

    def mark_completed_with_url(self, file_url: str):
        self.job.status = "completed"
        self.job.output_file_url = file_url
        self.add_log(f"Hoàn thành thu hoạch! File tại: {file_url}")
        self.db.commit()

    def mark_completed_with_data(self, data_string: str, format_type: str):
        """Lưu trạng thái completed và URL tải local"""
        self.job.status = "completed"
        self.job.output_file_url = f"/api/harvesting/jobs/{self.job_id}/download?format={format_type}"
        self.add_log("Hoàn thành thu hoạch và lưu trữ Database.")
        self.db.commit()

    def mark_failed(self, error_message: str):
        self.job.status = "failed"
        self.job.error_message = error_message
        self.add_log(f"LỖI: {error_message}")
        self.db.commit()