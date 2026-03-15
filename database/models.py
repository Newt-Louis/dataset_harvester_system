from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database.database import Base

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow)

    # Relationship: 1 user có nhiều api_configs
    api_configs   = relationship("ApiConfig", back_populates="owner", cascade="all, delete")


class ApiConfig(Base):
    __tablename__ = "api_configs"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider   = Column(String, nullable=False)
    api_key    = Column(String, nullable=False)   # Lưu encrypted (xem auth.py)
    model_name = Column(String, nullable=False)
    is_active  = Column(Boolean, default=True)

    # Relationship ngược lại
    owner = relationship("User", back_populates="api_configs")
