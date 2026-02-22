"""Application Layer Package

Application Layer - 应用服务层（用例 / orchestrator）

包含:
- common: 通用应用组件
- commands: 命令处理器(写)
- queries: 查询处理器(查)
"""

from pingpong_service.app.application.modules import ApplicationModule

__all__ = ["ApplicationModule"]