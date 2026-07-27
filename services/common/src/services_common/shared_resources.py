from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from services_common.resource_keys import db_key, redis_key


AsyncCloser = Callable[[Any], Awaitable[None]]


@dataclass
class _ResourceEntry:
    resource: Any
    closer: AsyncCloser | None = None
    owned_by_container: bool = True


class SharedResources:
    """Shared resource registry.

    Keys are intentionally generic to support future shared resources, e.g.:
    - db:default
    - redis:default
    - db:analytics
    - resource:mongo:default
    """

    def __init__(self) -> None:
        self._resources: dict[str, _ResourceEntry] = {}

    def register(
        self,
        key: str,
        resource: Any,
        *,
        closer: AsyncCloser | None = None,
        owned_by_container: bool = True,
    ) -> Any:
        self._resources[key] = _ResourceEntry(
            resource=resource,
            closer=closer,
            owned_by_container=owned_by_container,
        )
        return resource

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._resources.get(key)
        return entry.resource if entry else default

    def require(self, key: str) -> Any:
        entry = self._resources.get(key)
        if entry is None:
            raise KeyError(f"Shared resource not found: {key}")
        return entry.resource

    def get_or_create(
        self,
        key: str,
        factory: Callable[[], Any],
        *,
        closer: AsyncCloser | None = None,
        owned_by_container: bool = True,
    ) -> Any:
        existing = self.get(key)
        if existing is not None:
            return existing
        resource = factory()
        return self.register(key, resource, closer=closer, owned_by_container=owned_by_container)

    def get_db(self, name: str = "default") -> Any:
        return self.get(db_key(name))

    def get_redis(self, name: str = "default") -> Any:
        return self.get(redis_key(name))

    async def close_all(self) -> None:
        for key in reversed(list(self._resources.keys())):
            entry = self._resources[key]
            if entry.owned_by_container and entry.closer is not None:
                await entry.closer(entry.resource)
