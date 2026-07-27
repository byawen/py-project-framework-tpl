"""业务码测试查询

用于验证 biz_code 从 application 层异常透传到 API 响应的完整链路。
"""
from dataclasses import dataclass

from pingpong_service.app.application.common.exception import RegistrationFailedException


@dataclass
class BizCodeTestResult:
    """测试查询结果（正常情况下不会返回，因为会先抛异常）"""
    message: str


class BizCodeTestQuery:
    """业务码测试查询处理器 - 主动抛出应用异常"""

    async def execute(self) -> BizCodeTestResult:
        """执行测试 - 直接抛出 RegistrationFailedException"""
        raise RegistrationFailedException("这是来自 application 层的 biz_code 集成测试")