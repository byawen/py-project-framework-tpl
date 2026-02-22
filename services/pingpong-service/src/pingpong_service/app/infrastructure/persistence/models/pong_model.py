"""SQLAlchemy Pong 模型模块

Pong ORM 模型 - 对应数据库表
"""
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from services_common.database import BaseModel


class PongModel(BaseModel):
    """SQLAlchemy Pong 模型"""
    __tablename__ = "pipo_pong"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Pong(id={self.id}, data={self.data})>"
