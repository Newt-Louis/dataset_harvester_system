import json, csv, io, os
from datetime import datetime
from core.settings import settings

try:
    import boto3
    HAS_S3 = True
except ImportError:
    HAS_S3 = False


class StorageManager:
    LOCAL_DATA_DIR = "downloads"

    @classmethod
    def get_user_dir(cls, username: str) -> str:
        """Đảm bảo thư mục riêng của user luôn tồn tại trên Render/Server"""
        user_path = os.path.join(cls.LOCAL_DATA_DIR, username)
        if not os.path.exists(user_path):
            os.makedirs(user_path, exist_ok=True)
        return user_path

    @classmethod
    def delete_job_files(cls, username: str, job_id: int):
        """Xóa sạch các file liên quan đến Job ID của user để giải phóng bộ nhớ"""
        user_dir = os.path.join(cls.LOCAL_DATA_DIR, username)
        if not os.path.exists(user_dir):
            return
        
        # Tìm các file có định dạng dataset_job_{job_id}...
        prefix = f"dataset_job_{job_id}"
        for filename in os.listdir(user_dir):
            if filename.startswith(prefix):
                file_path = os.path.join(user_dir, filename)
                try:
                    os.remove(file_path)
                    print(f"🗑️ Đã xóa file rác: {file_path}")
                except Exception as e:
                    print(f"⚠️ Không thể xóa file {file_path}: {e}")

    @classmethod
    def append_to_local_file(cls, job_id: int, data_chunk: list, format_type: str, username: str) -> str:
        """Ghi nối dữ liệu vào file vật lý trong thư mục của user ngay khi sinh xong"""
        if not data_chunk:
            return ""

        user_dir = cls.get_user_dir(username)
        file_path = os.path.join(user_dir, f"dataset_job_{job_id}.{format_type}")

        file_exists = os.path.exists(file_path)

        with open(file_path, 'a', encoding='utf-8') as f:
            if format_type == "jsonl":
                for item in data_chunk:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            elif format_type == "csv":
                writer = csv.DictWriter(f, fieldnames=data_chunk[0].keys())
                if not file_exists or os.path.getsize(file_path) == 0:
                    writer.writeheader()
                writer.writerows(data_chunk)

        return file_path

    @staticmethod
    def _upload_to_s3(file_path: str, file_name: str, format_type: str, username: str) -> str:
        """Đẩy file lên S3 vào thư mục tên username"""
        s3_client = boto3.client('s3',
                                 endpoint_url=settings.S3_ENDPOINT,
                                 aws_access_key_id=settings.S3_ACCESS_KEY,
                                 aws_secret_access_key=settings.S3_SECRET_KEY
                                 )
        content_type = 'text/csv' if format_type == 'csv' else 'application/jsonl'
        
        # Key trên S3 sẽ là: username/dataset_job_...
        s3_key = f"{username}/{file_name}"
        
        s3_client.upload_file(
            file_path,
            settings.S3_BUCKET_NAME,
            s3_key,
            ExtraArgs={'ContentType': content_type}
        )
        return f"{settings.S3_PUBLIC_URL}/{s3_key}"

    @classmethod
    def finalize_dataset(cls, tracker, format_type: str):
        """Đẩy file lên S3 (nếu có) hoặc giữ nguyên local"""
        # Lấy username từ quan hệ owner của Job
        username = tracker.job.owner.username or f"user_{tracker.job.user_id}"
        user_dir = os.path.join(cls.LOCAL_DATA_DIR, username)
        file_path = os.path.join(user_dir, f"dataset_job_{tracker.job_id}.{format_type}")

        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            tracker.mark_failed("Không có dữ liệu để chốt sổ.")
            return

        file_name = f"dataset_job_{tracker.job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}"

        # Try S3
        if HAS_S3 and settings.S3_BUCKET_NAME and settings.S3_ACCESS_KEY:
            try:
                print(f"☁️ Đang tải file lên S3 cho user {username}...")
                url = cls._upload_to_s3(file_path, file_name, format_type, username)
                tracker.mark_completed_with_url(url)
                return
            except Exception as e:
                print(f"⚠️ Lỗi S3 ({e}). Giữ file local.")

        # Nếu không có S3 --> trả về link dowmload local
        tracker.mark_completed_with_data("", format_type)
