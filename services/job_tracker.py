from sqlalchemy.orm import Session
from database.models import HarvestJob

class JobTracker:
    def __init__(self, db: Session, job_id: int):
        self.db = db
        self.job_id = job_id
        self.job = self.db.query(HarvestJob).get(job_id)

    def update_model(self, model_name: str):
        if self.job.current_model != model_name:
            self.job.current_model = model_name
            self.db.commit()

    def add_progress(self, new_samples: int):
        self.job.samples_generated += new_samples
        self.db.commit()

    def mark_completed_with_url(self, file_url: str):
        self.job.status = "completed"
        self.job.output_file_url = file_url
        self.db.commit()

    def mark_completed_with_data(self, data_string: str, format_type: str):
        self.job.status = "completed"
        self.job.result_data = data_string
        # Đường dẫn ảo móc vào API tải file của ta
        self.job.output_file_url = f"/api/jobs/{self.job_id}/download?format={format_type}"
        self.db.commit()

    def mark_failed(self, error_message: str):
        self.job.status = "failed"
        self.job.error_message = error_message
        self.db.commit()