"""Local API 实现 — all-in-one 模式下直接调用"""


class LocalUserService:
    """本地用户服务实现"""

    async def get_user_by_id(self, user_id: str):
        # all-in-one 模式下的本地调用实现
        pass

    async def update_user_name(self, user_id: str, name: str) -> None:
        # all-in-one 模式下的本地调用实现
        pass
