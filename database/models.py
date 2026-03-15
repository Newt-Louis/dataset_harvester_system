from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    api_configs   = relationship("ApiConfig", back_populates="owner", cascade="all, delete")
    harvest_histories = relationship("HarvestHistory", back_populates="owner", cascade="all, delete-orphan")


class ApiConfig(Base):
    __tablename__ = "api_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)
    api_key = Column(String, nullable=False)   # Lưu encrypted (xem security.py)
    model_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationship ngược lại
    owner = relationship("User", back_populates="api_configs")

class HarvesterState(Base):
    __tablename__ = "harvester_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Lưu các state của giao diện Harvester.vue
    prompt = Column(Text, default="")
    seeds = Column(Text, default="")
    output_format = Column(String, default="jsonl")
    output_schema = Column(Text, default="")
    samples = Column(Integer, default=10)

    owner = relationship("User", back_populates="harvester_state")


class HarvestHistory(Base):
    __tablename__ = "harvest_histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Lưu lại toàn bộ nội dung user đã submit để sau này làm Dataset
    prompt = Column(Text, nullable=False)
    seeds = Column(Text, nullable=False)
    output_format = Column(String, nullable=False)
    output_schema = Column(Text, nullable=False)
    samples = Column(Integer, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="harvest_histories")