from typing import Any

import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from database.database import get_db
import os
from database import models

SECRET_KEY = os.getenv("JWT_SECRET", "change-this-to-a-long-random-string")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# Fernet key để encrypt/decrypt API key của user
FERNET_KEY = os.getenv("FERNET_KEY", "").encode()
fernet = Fernet(FERNET_KEY) if FERNET_KEY else None

bearer_scheme = HTTPBearer()
bearer_scheme_optional = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_bytes.decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    plain_bytes = plain.encode('utf-8')
    hashed_bytes = hashed.encode('utf-8')
    return bcrypt.checkpw(plain_bytes, hashed_bytes)

# ---------------------------------------------------------------
# JWT
# ---------------------------------------------------------------
def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> int:
    """Trả về user_id từ token, raise exception nếu invalid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn"
        )

# ---------------------------------------------------------------
# Dependency: lấy current user từ Bearer token
# ---------------------------------------------------------------
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    user_id = decode_token(credentials.credentials)
    user: Any | None = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Không tìm thấy user")
    return user

def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme_optional),
    db: Session = Depends(get_db)
):
    if not credentials:
        return None

    try:
        user_id = decode_token(credentials.credentials)
        return db.query(models.User).filter(models.User.id == user_id).first()
    except HTTPException:
        return None

# ---------------------------------------------------------------
# Encrypt / Decrypt API Key
# ---------------------------------------------------------------
def encrypt_api_key(raw_key: str) -> str:
    if not fernet:
        return raw_key  # Fallback nếu chưa cấu hình FERNET_KEY
    return fernet.encrypt(raw_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    if not fernet:
        return encrypted_key
    return fernet.decrypt(encrypted_key.encode()).decode()
