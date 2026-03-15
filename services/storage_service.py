import json, csv, io, os
from datetime import datetime
from core.settings import settings

# Import tùy chọn (Không bắt ép user phải cài nếu họ không xài mây)
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    HAS_GDRIVE = True
except ImportError:
    HAS_GDRIVE = False

try:
    import boto3

    HAS_S3 = True
except ImportError:
    HAS_S3 = False


class StorageManager:
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
    def _upload_to_gdrive(content_string: str, file_name: str, format_type: str) -> str:
        """Bắn file lên Google Drive, trả về URL xem file"""
        scopes = ['https://www.googleapis.com/auth/drive.file']
        creds = service_account.Credentials.from_service_account_file(
            settings.GDRIVE_CREDENTIALS_PATH, scopes=scopes)

        service = build('drive', 'v3', credentials=creds)

        # Biến chuỗi text thành đối tượng File-like trong RAM
        media = MediaIoBaseUpload(io.BytesIO(content_string.encode('utf-8')),
                                  mimetype='text/csv' if format_type == 'csv' else 'application/jsonl')

        file_metadata = {'name': file_name, 'parents': [settings.GDRIVE_FOLDER_ID]}

        uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return uploaded_file.get('webViewLink')  # Trả về link Drive để click vào xem luôn

    @staticmethod
    def _upload_to_s3(content_string: str, file_name: str, format_type: str) -> str:
        """Bắn file lên S3, trả về URL tải xuống"""
        s3_client = boto3.client('s3',
                                 endpoint_url=settings.S3_ENDPOINT,
                                 aws_access_key_id=settings.S3_ACCESS_KEY,
                                 aws_secret_access_key=settings.S3_SECRET_KEY
                                 )
        content_type = 'text/csv' if format_type == 'csv' else 'application/jsonl'
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=file_name,
            Body=content_string.encode('utf-8'),
            ContentType=content_type
        )
        # Ghép URL gốc với tên file
        return f"{settings.S3_PUBLIC_URL}/{file_name}"

    @classmethod
    def save_dataset(cls, tracker, data: list, format_type: str):
        """Cơ chế Thác Đổ: GDrive -> S3 -> Database"""
        content = cls._convert_to_string(data, format_type)
        if not content:
            tracker.mark_failed("Không có dữ liệu hợp lệ để lưu.")
            return

        file_name = f"dataset_job_{tracker.job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}"

        # 1. THỬ GOOGLE DRIVE
        if HAS_GDRIVE and settings.GDRIVE_FOLDER_ID and os.path.exists(settings.GDRIVE_CREDENTIALS_PATH):
            try:
                print("☁️ Đang lưu lên Google Drive...")
                url = cls._upload_to_gdrive(content, file_name, format_type)
                tracker.mark_completed_with_url(url)
                return
            except Exception as e:
                print(f"⚠️ Lỗi Google Drive ({e}). Chuyển sang phương án dự phòng...")

        # 2. THỬ S3
        if HAS_S3 and settings.S3_BUCKET_NAME and settings.S3_ACCESS_KEY:
            try:
                print("☁️ Đang lưu lên S3 Object Storage...")
                url = cls._upload_to_s3(content, file_name, format_type)
                tracker.mark_completed_with_url(url)
                return
            except Exception as e:
                print(f"⚠️ Lỗi S3 ({e}). Chuyển sang phương án Database...")

        # 3. LƯU DATABASE (CỨU CÁNH CUỐI CÙNG - KHÔNG BAO GIỜ THẤT BẠI)
        print("💾 Đang lưu trực tiếp vào Database...")
        tracker.mark_completed_with_data(content, format_type)