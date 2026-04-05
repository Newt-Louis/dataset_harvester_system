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
    def append_to_local_file(cls, job_id: int, data_chunk: list, format_type: str) -> str:
        """Ghi nối dữ liệu vào file vật lý trên server ngay khi sinh xong"""
        if not data_chunk:
            return ""

        os.makedirs(cls.LOCAL_DATA_DIR, exist_ok=True)
        file_path = os.path.join(cls.LOCAL_DATA_DIR, f"dataset_job_{job_id}.{format_type}")

        # Kiểm tra file đã tồn tại hay chưa (để xử lý header cho CSV)
        file_exists = os.path.exists(file_path)

        with open(file_path, 'a', encoding='utf-8') as f:
            if format_type == "jsonl":
                for item in data_chunk:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            elif format_type == "csv":
                writer = csv.DictWriter(f, fieldnames=data_chunk[0].keys())
                # Chỉ ghi Header nếu file mới được tạo lần đầu
                if not file_exists or os.path.getsize(file_path) == 0:
                    writer.writeheader()
                writer.writerows(data_chunk)

        return file_path

    @staticmethod
    def _convert_to_string(data: list, format_type: str) -> str:
        """Biến mảng JSON thành chuỗi trong RAM"""
        if not data: return ""
        if format_type == "jsonl":
            return "\n".join([json.dumps(item, ensure_ascii=False) for item in data])
        elif format_type == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return output.getvalue()
        return ""

    @staticmethod
    def _upload_to_s3(file_path: str, file_name: str, format_type: str) -> str:
        """Bắn file lên S3, trả về URL tải xuống"""
        s3_client = boto3.client('s3',
                                 endpoint_url=settings.S3_ENDPOINT,
                                 aws_access_key_id=settings.S3_ACCESS_KEY,
                                 aws_secret_access_key=settings.S3_SECRET_KEY
                                 )
        content_type = 'text/csv' if format_type == 'csv' else 'application/jsonl'
        s3_client.upload_file(
            file_path,
            settings.S3_BUCKET_NAME,
            file_name,
            ExtraArgs={'ContentType': content_type}
        )
        # Ghép URL gốc với tên file
        return f"{settings.S3_PUBLIC_URL}/{file_name}"

    @classmethod
    def finalize_dataset(cls, tracker, format_type: str):
        """Hàm chốt sổ: Đẩy file từ Server lên Cloud (nếu có) hoặc lưu vào DB"""
        file_path = os.path.join(cls.LOCAL_DATA_DIR, f"dataset_job_{tracker.job_id}.{format_type}")

        # Kiểm tra xem file có tồn tại và có dữ liệu không
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            tracker.mark_failed("Quá trình kết thúc nhưng không có dữ liệu hợp lệ được sinh ra.")
            return

        file_name = f"dataset_job_{tracker.job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}"

        # 1. THỬ S3
        if HAS_S3 and settings.S3_BUCKET_NAME and settings.S3_ACCESS_KEY:
            try:
                print("☁️ Đang tải file local lên S3...")
                url = cls._upload_to_s3(file_path, file_name, format_type)
                tracker.mark_completed_with_url(url)
                return
            except Exception as e:
                print(f"⚠️ Lỗi S3 ({e}). Chuyển sang phương án Database...")

        # 2. LƯU DATABASE (Đọc ngược file lên lại RAM và lưu vào cột dữ liệu)
        print("💾 Đang đọc file local và lưu trực tiếp vào Database...")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        tracker.mark_completed_with_data(content, format_type)