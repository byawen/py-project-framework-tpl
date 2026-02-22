"""健康检查模块

提供应用健康检查功能，支持数据库、Redis 等依赖服务的检查。
"""
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class HealthStatus(str, Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ServiceHealth:
    """服务健康状态"""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    response_time_ms: Optional[float] = None


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    status: HealthStatus
    services: list[ServiceHealth]
    overall_response_time_ms: Optional[float] = None

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "status": self.status.value,
            "services": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "message": s.message,
                    "response_time_ms": s.response_time_ms,
                }
                for s in self.services
            ],
            "response_time_ms": self.overall_response_time_ms,
        }


class HealthChecker:
    """健康检查器

    使用示例:

        checker = HealthChecker()
        checker.add_check("database", database_manager)
        checker.add_check("redis", redis_manager)

        result = await checker.check_all()
    """

    def __init__(self):
        self._checks: dict[str, callable] = {}

    def add_database_check(self, name: str, db_manager) -> None:
        """添加数据库健康检查

        Args:
            name: 检查项名称
            db_manager: DatabaseManager 实例
        """
        async def check():
            import time
            start = time.perf_counter()
            try:
                async with db_manager.session_maker() as session:
                    await session.execute("SELECT 1")
                response_time = (time.perf_counter() - start) * 1000
                return ServiceHealth(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message="Database connection is healthy",
                    response_time_ms=response_time,
                )
            except Exception as e:
                return ServiceHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Database connection failed: {str(e)}",
                )

        self._checks[name] = check

    def add_redis_check(self, name: str, redis_manager) -> None:
        """添加 Redis 健康检查

        Args:
            name: 检查项名称
            redis_manager: RedisManager 实例
        """
        async def check():
            import time
            start = time.perf_counter()
            try:
                is_healthy = await redis_manager.health_check()
                response_time = (time.perf_counter() - start) * 1000
                if is_healthy:
                    return ServiceHealth(
                        name=name,
                        status=HealthStatus.HEALTHY,
                        message="Redis connection is healthy",
                        response_time_ms=response_time,
                    )
                else:
                    return ServiceHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message="Redis ping failed",
                    )
            except Exception as e:
                return ServiceHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Redis connection failed: {str(e)}",
                )

        self._checks[name] = check

    def add_custom_check(self, name: str, check_func: callable) -> None:
        """添加自定义健康检查

        Args:
            name: 检查项名称
            check_func: 异步检查函数，返回 ServiceHealth
        """
        self._checks[name] = check_func

    async def check_all(self) -> HealthCheckResult:
        """执行所有健康检查

        Returns:
            HealthCheckResult: 健康检查结果
        """
        import time

        start = time.perf_counter()
        services = []

        for name, check_func in self._checks.items():
            try:
                result = await check_func()
                services.append(result)
            except Exception as e:
                services.append(
                    ServiceHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Check failed: {str(e)}",
                    )
                )

        overall_time = (time.perf_counter() - start) * 1000

        # 判断整体状态
        if all(s.status == HealthStatus.HEALTHY for s in services):
            status = HealthStatus.HEALTHY
        elif any(s.status == HealthStatus.UNHEALTHY for s in services):
            status = HealthStatus.UNHEALTHY
        else:
            status = HealthStatus.DEGRADED

        return HealthCheckResult(
            status=status,
            services=services,
            overall_response_time_ms=overall_time,
        )
