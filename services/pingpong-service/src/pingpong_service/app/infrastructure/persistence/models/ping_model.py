"""SQLAlchemy Ping 模型模块

Ping ORM 模型 - 对应数据库表
"""
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from services_common.database import BaseModel


class PingModel(BaseModel):
    """SQLAlchemy Ping 模型"""
    __tablename__ = "pipo_ping"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self) -> str:
        return f"<Ping(id={self.id}, message={self.message})>"
