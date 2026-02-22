"""创建 Pong 命令模块

创建 Pong 命令处理器
"""
from dataclasses import dataclass
from typing import Optional
from injector import inject
from pingpong_service.app.domain.entities.ping import Pong
from pingpong_service.app.domain.repositories.pong_repository import PongRepository
from pingpong_service.app.domain.value_objects.pong_data import PongData
from pingpong_service.foundation.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PongCommandResult:
    """Pong 命令执行结果"""
    data: str
    pong: Optional[Pong] = None


class PongCommand:
    """创建 Pong 命令处理器"""
    
    @inject
    def __init__(self, pong_repository: PongRepository):
        self.pong_repository = pong_repository
    
    async def execute(self, data: str) -> PongCommandResult:
        """执行创建 Pong 命令"""
        logger.info(f"Creating pong with data: {data}")
        
        # 创建 PongData 值对象
        pong_data = PongData(data)
        
        # 创建 Pong 实体
        pong = Pong(data=pong_data)
        
        # 保存到仓储
        saved_pong = await self.pong_repository.save(pong)
        
        logger.info(f"Pong created with id: {saved_pong.id}")
        
        return PongCommandResult(
            data=data,
            pong=saved_pong,
        )
