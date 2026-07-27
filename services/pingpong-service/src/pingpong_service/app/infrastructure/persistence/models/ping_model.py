"""SQLAlchemy Ping 模型模块

Ping ORM 模型 - 对应数据库表
"""
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from services_common.database import BaseModel


class PIPOPingModel(BaseModel):
    """SQLAlchemy Ping 模型（类名带服务前缀 PIPO 全大写，表名 pipo_ 全小写）"""
    __tablename__ = "pipo_ping"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ping_id: Mapped[str] = mapped_column(String(36), nullable=False, comment="业务ID")
    message: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<Ping(id={self.id}, message={self.message})>"
