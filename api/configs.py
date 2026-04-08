from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database.database import get_db
from core.security import get_current_user, encrypt_api_key, decrypt_api_key
from database import models
from schemas.payloads import TestModelRequest, ConfigCreate, ConfigResponse, ConfigResponseWithKey
from services.test_models import run_model_test
from utils.normalize import mask_key

router = APIRouter(prefix="/api/configs", tags=["configs"])

@router.get("", response_model=List[ConfigResponseWithKey])
def get_configs(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lấy tất cả configs của user hiện tại."""
    configs = db.query(models.ApiConfig).filter(
        models.ApiConfig.user_id == current_user.id
    ).all()

    result = []
    for c in configs:
        decrypted = decrypt_api_key(c.api_key)
        base = ConfigResponse.model_validate(c)
        result.append(ConfigResponseWithKey(
            **base.model_dump(),
            api_key_masked=mask_key(decrypted)
        ))
    return result


@router.post("", response_model=ConfigResponseWithKey)
def add_config(
    req: ConfigCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    prefix = req.provider.lower()
    if(prefix == "openai"):
        normalized = req.model_name
    else:
        normalized = prefix+ '/' +req.model_name
    """Thêm config mới cho user hiện tại."""
    config = models.ApiConfig(
        user_id=current_user.id,
        provider=req.provider,
        api_key=encrypt_api_key(req.api_key),  # Encrypt trước khi lưu
        model_name=normalized,
        is_active=True
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    return ConfigResponseWithKey(
        id=config.id,
        provider=config.provider,
        model_name=normalized,
        is_active=config.is_active,
        api_key_masked=mask_key(req.api_key)
    )


@router.patch("/{config_id}/toggle")
def toggle_config(
    config_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bật/tắt một config."""
    config = db.query(models.ApiConfig).filter(
        models.ApiConfig.id == config_id,
        models.ApiConfig.user_id == current_user.id  # Bảo đảm chỉ sửa của mình
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Không tìm thấy config")

    config.is_active = not config.is_active
    db.commit()
    return {"id": config.id, "is_active": config.is_active}


@router.delete("/{config_id}")
def delete_config(
    config_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Xóa một config."""
    config = db.query(models.ApiConfig).filter(
        models.ApiConfig.id == config_id,
        models.ApiConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Không tìm thấy config")

    db.delete(config)
    db.commit()
    return {"detail": "Đã xóa"}

@router.post("/{config_id}/test")
async def test_model_connection(
        config_id: int,
        req: TestModelRequest,
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    config = db.query(models.ApiConfig).filter(
        models.ApiConfig.id == config_id,
        models.ApiConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình API Key này.")

    real_api_key = decrypt_api_key(config.api_key) # type: ignore[arg-type]

    result = await run_model_test(
        model_name=config.model_name, # type: ignore[arg-type]
        api_key=real_api_key,
        payload=req
    )

    return result