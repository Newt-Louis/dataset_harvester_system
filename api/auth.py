from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from database.database import get_db
from database import models
from core import security

router = APIRouter(prefix="/auth", tags=["Auth"])

# ---------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    # Kiểm tra email đã tồn tại chưa
    existing = db.query(models.User).filter(models.User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email đã được đăng ký")

    # Tạo user mới
    user = models.User(
        email=req.email,
        hashed_password=security.hash_password(req.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = security.create_access_token(user.id)
    return {"access_token": token}


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email).first()

    if not user or not security.verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

    token = security.create_access_token(user.id)
    return {"access_token": token}


@router.get("/me")
def get_me(current_user: models.User = Depends(security.get_current_user)):
    """Kiểm tra token còn hợp lệ không, trả về thông tin user."""
    return {"id": current_user.id, "email": current_user.email}
