"""用户资料数据模型"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, JSON, DateTime, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)

    # 固定字段
    avatar_url = Column(String(512), nullable=True)
    nickname = Column(String(64), nullable=True)
    age = Column(String(8), nullable=True)
    occupation = Column(String(128), nullable=True)
    region = Column(String(64), nullable=True)
    languages = Column(JSON, default=list)
    demand_types = Column(JSON, default=list)

    # AI 产出
    tags = Column(JSON, default=dict)
    bio = Column(String(1024), nullable=True)

    # 元信息
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
