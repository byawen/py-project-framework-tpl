"""幂等控制模块 - 基于 Redis 的请求幂等保障

设计要点
--------
- 装饰器 ``@idempotent(...)`` 在路由定义时声明幂等控制，按需从多个来源组合幂等 key：
  请求头 (header) / Authorization 解析出的 account_id / 请求体字段 (body_field)。
- **请求时幂等**（默认，``commit_on_success=False``）：``SET NX EX`` 原子获取 Redis 锁，
  执行处理；成功则缓存响应，异常则释放锁允许重试。重复请求（TTL 内相同 key）：命中缓存
  返回首次响应；处理中返回 409。
- **响应成功后再幂等**（``commit_on_success=True``）：不预先抢锁，并发重复请求都会执行；
  仅处理成功后才写入幂等键 + 缓存响应，后续相同请求命中返回缓存/409；处理失败不上锁
  （允许重试）。适用于"成功后短时间内不再重复触发"的场景（如发送短信验证码）。
- **fail-open**：Redis 不可用、key 无法解析时一律不阻塞请求进入（符合「Redis 不可用不影响 API」的要求）。

来源解析规则
------------
- ``header``（默认 ``X-Request-ID``）是**强制幂等锚点**：打开幂等后，header 必须有值
  幂等才生效。中间件在缺失时会回填随机值，故默认始终可用——但这也意味着 header 非 None
  时它**始终参与 key**，要做到"纯按业务字段幂等"（与 X-Request-ID 无关）须显式传
  ``header=None``。
- ``account_id`` / ``body_field`` 是**可选作用域增强**：有值时与 header **一起**组 key
  （按账号 / 业务实体隔离同一 header 值）；取不到值则跳过，不影响 header 的幂等基础。
- ``header=None``（显式关闭请求头锚点）→ 改以 ``body_field`` / ``account_id`` 中首个
  有值者作锚点（纯按业务字段幂等）；二者均无值 → fail-open（不阻塞）。
- key 自动包含 ``method`` + ``path``，避免不同路由相同来源值产生跨路由误判。

用法
----

    from services_common import idempotent

    # 1) 最简：默认用 X-Request-ID 做幂等键，60s 窗口
    @router.post("/tasks")
    @idempotent()
    async def create_task(request: CreateTaskRequest, http_request: Request):
        ...

    # 2) 指定窗口 + 按 account_id 隔离 + 取 body 中的 order_no
    @router.post("/orders")
    @idempotent(expire_seconds=300, account_id=True, body_field="order_no")
    async def create_order(...):
        ...

    # 3) 用自定义请求头作为幂等键
    @router.post("/payments")
    @idempotent(expire_seconds=600, header="X-Idempotency-Key")
    async def create_payment(...):
        ...

    # 4) 响应成功后再幂等（commit_on_success）：
    #    不预先抢锁，并发重复请求都会执行；只有处理成功后才写入幂等键 +
    #    缓存响应，后续相同请求命中返回缓存/409。适用于"成功后短时间内不再重复
    #    触发"的场景（如发送短信验证码：不阻塞首次/并发请求，但已发送成功的
    #    手机号 60s 内不再重复发送）。
    @router.post("/sms/send-code")
    @idempotent(expire_seconds=60, body_field="phone", commit_on_success=True)
    async def send_code(...):
        ...

    # 5) 纯按业务字段幂等（header=None）：忽略 X-Request-ID，同一 phone 在窗口内
    #    重复请求命中幂等，避免调用方不复用同一 X-Request-ID 时幂等 miss 而穿透到
    #    下游（如触发短信服务商流控）。
    @router.post("/sms/send-code")
    @idempotent(expire_seconds=60, header=None, body_field="phone", commit_on_success=True)
    async def send_code(...):
        ...

启用前提
--------
装饰器 fail-open，未配置 Redis 时等价于直通。要让幂等真正生效，需在服务启动时
注册 Redis/Settings（每个服务 ``main.py`` 的 ``set_injector(_injector)`` 之后调用一次）::

    from services_common import configure_idempotency
    set_injector(_injector)
    configure_idempotency(injector=_injector)
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from services_common.jwt import try_parse_token_account_id
from services_common.logging import get_logger
from services_common.redis import RedisManager
from services_common.response import conflict
from services_common.config import Settings

logger = get_logger(__name__)

# 缓存响应体上限：超过则不缓存（重复请求回退为 409），避免 Redis 占用过大
_MAX_CACHE_BYTES = 64 * 1024


# =============================================================================
# 启动期注册：让 services_common 拿到本服务的 RedisManager / Settings
# =============================================================================
_registered_redis: Optional[RedisManager] = None
_registered_settings: Optional[Any] = None


def configure_idempotency(
    redis_manager: Optional[RedisManager] = None,
    settings: Optional[Any] = None,
    injector: Optional[Any] = None,
) -> None:
    """注册幂等控制所需的 Redis 连接与 Settings。

    可任选一种方式调用：

    - ``configure_idempotency(injector=_injector)`` —— 推荐，自动从注入器解析
      ``RedisManager`` 与 ``Settings``。
    - ``configure_idempotency(redis_manager=rm, settings=st)`` —— 显式传入。

    缺失的依赖不会抛错（幂等退化为 fail-open），便于分阶段接入。
    """
    global _registered_redis, _registered_settings

    if injector is not None:
        if redis_manager is None:
            try:
                redis_manager = injector.get(RedisManager)
            except Exception:  # noqa: BLE001 - 缺依赖不阻塞启动
                logger.warning("configure_idempotency: injector 中未取到 RedisManager")
        if settings is None:
            try:
                settings = injector.get(Settings)
            except Exception:  # noqa: BLE001
                logger.warning("configure_idempotency: injector 中未取到 Settings")

    if redis_manager is not None:
        _registered_redis = redis_manager
    if settings is not None:
        _registered_settings = settings


# =============================================================================
# 运行期解析
# =============================================================================
def _resolve_redis(req: Request, explicit: Optional[RedisManager]) -> Optional[RedisManager]:
    """解析 RedisManager：显式传入 > 启动期注册 > app.state.redis_manager。"""
    if explicit is not None:
        return explicit
    if _registered_redis is not None:
        return _registered_redis
    cand = getattr(req.app.state, "redis_manager", None)
    if isinstance(cand, RedisManager):
        return cand
    return None

def _resolve_settings(req: Request) -> Optional[Any]:
    """解析 Settings：启动期注册 > app.state.settings（所有服务都设置了）。"""
    if _registered_settings is not None:
        return _registered_settings
    return getattr(req.app.state, "settings", None)


async def _extract_account_id(req: Request, settings: Optional[Any]) -> str:
    """从 Authorization 头解析 JWT 的 account_id；任何异常返回空串（不阻塞）。"""
    auth = req.headers.get("authorization") or ""
    if not auth:
        return ""
    secret = getattr(settings, "JWT_SECRET_KEY", "secret-key") if settings else "secret-key"
    algo = getattr(settings, "JWT_ALGORITHM", "HS256") if settings else "HS256"
    try:
        return await try_parse_token_account_id(auth, "access", secret, algo)
    except Exception:  # noqa: BLE001
        return ""


async def _extract_body_field(req: Request, field: str) -> Optional[str]:
    """按 JSON 解析请求体取指定字段；非 JSON / 缺失返回 None（不阻塞）。

    注意：Starlette 的 ``Request.body()`` 会缓存已读 body，FastAPI 后续的 pydantic
    body 注入复用缓存，故此处先读 body 不会破坏路由的 body 解析。
    """
    try:
        body_bytes = await req.body()
    except Exception:  # noqa: BLE001
        return None
    if not body_bytes:
        return None
    try:
        data = json.loads(body_bytes)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    val = data.get(field)
    if val is None:
        return None
    return str(val)


def _serialize_result(result: Any) -> Optional[tuple[int, Any]]:
    """把 handler 返回值序列化为 ``(status_code, json_body)``；不可序列化返回 None。"""
    if isinstance(result, Response):
        try:
            return result.status_code, json.loads(result.body)
        except Exception:  # noqa: BLE001
            return None
    if isinstance(result, BaseModel):
        body = result.model_dump(mode="json")
        status = getattr(result, "code", 200)
        try:
            return int(status), body
        except (TypeError, ValueError):
            return 200, body
    # dict / list / 原始类型
    if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
        return 200, result
    return None


def _conflict_body() -> dict:
    """重复请求的 409 响应体，与全局 ErrorResponse 格式一致。"""
    body = conflict(message="重复请求，正在处理或已处理完成")
    dumped = body.model_dump(mode="json")
    # model_dump 会把 datetime 序列化为字符串，确保时间戳为当前请求时刻
    dumped["timestamp"] = datetime.now().isoformat()
    return dumped


# =============================================================================
# 装饰器
# =============================================================================
def _ensure_request_signature(func: Callable) -> tuple(inspect.Signature, bool):
    """构造包含 ``_idem_request: Request`` 的签名，返回 (新签名, 是否新增)。

    FastAPI 依据包装函数的 ``__signature__`` 做依赖注入；此处确保 Request 可被注入，
    即使原 handler 未声明 Request 参数（本仓库 handler 的 Request 参数命名不一）。
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    has_request = any(
        p.annotation is Request or p.annotation == "Request"
        for p in params
    )
    if not has_request:
        req_param = inspect.Parameter(
            "_idem_request",
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=Request,
        )
        # 插到 **kwargs 之前（若有）
        insert_at = len(params)
        for i, p in enumerate(params):
            if p.kind == inspect.Parameter.VAR_KEYWORD:
                insert_at = i
                break
        params.insert(insert_at, req_param)
        return sig.replace(parameters=params), True
    return sig, False


def _find_request(kwargs: dict, args: tuple) -> Optional[Request]:
    """从注入参数中定位 Request 实例。"""
    req = kwargs.get("_idem_request")
    if isinstance(req, Request):
        return req
    for v in list(kwargs.values()) + list(args):
        if isinstance(v, Request):
            return v
    return None


def _build_idempotency_key(
    *,
    req: Request,
    key_prefix: str,
    header: Optional[str],
    header_val: Optional[str],
    account_val: Optional[str],
    body_field: Optional[str],
    body_val: Optional[str],
) -> Optional[str]:
    """组合幂等 key。

    锚点策略：

    - ``header`` 非 None（默认 ``X-Request-ID``）：header 为**强制锚点**，必须有值才
      返回 key，否则 fail-open；``account_id`` / ``body_field`` 为可选增强，有值时追加。
      注意：中间件会给缺失的 ``X-Request-ID`` 回填随机值，故 header 非 None 时它
      **始终参与 key**——要做到"纯按业务字段幂等"（与 X-Request-ID 无关），须显式
      传 ``header=None``。
    - ``header`` 显式为 None：不使用请求头，改以 ``body_field`` / ``account_id`` 中首个
      有值者作锚点（实现"纯按业务字段幂等"，如发送短信按 phone、与 X-Request-ID 无关）；
      二者均无值 → fail-open。

    key 自动包含 ``method`` + ``path``，避免不同路由相同来源值产生跨路由误判。
    """
    sources: list[str] = [f"m={req.method}", f"p={req.url.path}"]

    if header is not None:
        # ── header 强制锚点：没值就 fail-open ──
        if not header_val:
            return None
        sources.append(f"h={header_val}")
        if account_val:
            sources.append(f"a={account_val}")
        if body_field is not None and body_val:
            sources.append(f"b={body_field}={body_val}")
    else:
        # ── 无 header：以 body_field / account_id 作锚点（纯按业务字段幂等）──
        if body_field is not None and body_val:
            sources.append(f"b={body_field}={body_val}")
            if account_val:
                sources.append(f"a={account_val}")
        elif account_val:
            sources.append(f"a={account_val}")
        else:
            return None  # 无可用锚点 → fail-open

    combined = "|".join(sources)
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return f"idem:{key_prefix}:{digest}"


def idempotent(
    expire_seconds: int = 60,
    header: Optional[str] = "X-Request-ID",
    account_id: bool = False,
    body_field: Optional[str] = None,
    key_prefix: str = "default",
    commit_on_success: bool = False,
    redis_manager: Optional[RedisManager] = None,
):
    """路由幂等控制装饰器。

    Args:
        expire_seconds: 幂等窗口（秒），默认 60。
        header: 取值请求头名作为**强制幂等锚点**，默认 ``X-Request-ID``（中间件保证存在）。
          传 ``None`` 则不使用请求头，改以 ``body_field`` / ``account_id`` 作锚点（实现
          "纯按业务字段幂等"，如发送短信按 phone、与 X-Request-ID 无关；二者均无值则
          fail-open）。注意：header 非 None 时中间件回填的随机 X-Request-ID 会始终
          参与 key，要做到与该头无关必须显式 ``header=None``。
        account_id: 是否从 Authorization 解析 account_id 纳入 key（按账号隔离）。
        body_field: 从 JSON 请求体取该字段纳入 key；注意仅支持 JSON 请求体。
        key_prefix: key 命名空间，默认 ``default``；不同业务可用不同前缀隔离。
        commit_on_success: 幂等时机。默认 ``False`` = 请求时幂等（先抢锁，处理中重复
          请求立即 409，成功后缓存响应）。``True`` = 响应成功后再幂等：不预先抢锁，
          并发重复请求都会执行，仅处理成功后才写入幂等键并缓存响应，后续相同请求
          命中返回缓存/409；处理失败不上锁（允许重试）。适用于"成功后短时间内不再
          重复触发"的场景（如发送短信验证码）。
        redis_manager: 显式指定 RedisManager（一般不用，留给测试/特殊场景）。

    装饰器 fail-open：Redis 不可用或 key 无法解析时不阻塞请求。
    """
    # 支持 @idempotent 无括号用法
    if callable(expire_seconds) and not isinstance(expire_seconds, bool):
        func = expire_seconds  # type: ignore[assignment]
        return _make_wrapper(
            func,
            expire_seconds=60,
            header="X-Request-ID",
            account_id=False,
            body_field=None,
            key_prefix="default",
            commit_on_success=False,
            explicit_redis=None,
        )

    def decorator(func: Callable) -> Callable:
        return _make_wrapper(
            func,
            expire_seconds=expire_seconds,
            header=header,
            account_id=account_id,
            body_field=body_field,
            key_prefix=key_prefix,
            commit_on_success=commit_on_success,
            explicit_redis=redis_manager,
        )

    return decorator


def _make_wrapper(
    func: Callable,
    *,
    expire_seconds: int,
    header: Optional[str],
    account_id: bool,
    body_field: Optional[str],
    key_prefix: str,
    commit_on_success: bool,
    explicit_redis: Optional[RedisManager],
) -> Callable:
    new_sig, _added = _ensure_request_signature(func)

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        req = _find_request(kwargs, args)

        # 无 Request 可用 → 无法做幂等，直通
        if req is None:
            return await _call_func(func, *args, **kwargs)

        # ── 解析各来源（取不到的跳过，不 fail-open）──
        header_val = req.headers.get(header) if header else None
        account_val: Optional[str] = None
        if account_id:
            settings = _resolve_settings(req)
            account_val = await _extract_account_id(req, settings)
            if not account_val:
                # 取不到 → 该来源不参考，降级为其他来源（如 header）做幂等
                account_val = None
        body_val: Optional[str] = None
        if body_field:
            body_val = await _extract_body_field(req, body_field)
            if not body_val:
                # 取不到 → 该来源不参考
                body_val = None

        lock_key = _build_idempotency_key(
            req=req,
            key_prefix=key_prefix,
            header=header,
            header_val=header_val,
            account_val=account_val,
            body_field=body_field,
            body_val=body_val,
        )
        if lock_key is None:
            # header 锚点缺失（或 header=None）→ fail-open
            logger.debug("idempotent: 幂等锚点(header)缺失，fail-open", extra={"path": req.url.path})
            return await _call_func(func, *args, **kwargs)

        redis = _resolve_redis(req, explicit_redis)
        if redis is None:
            # Redis 未配置/不可用 → fail-open（不阻塞 API）
            logger.warning("idempotent: Redis 不可用，fail-open", extra={"path": req.url.path})
            return await _call_func(func, *args, **kwargs)

        resp_key = f"{lock_key}:resp"

        # ── commit_on_success：响应成功后再幂等 ──
        # 不预先抢锁：并发重复请求都会执行；仅处理成功后才写入幂等键 + 缓存响应，
        # 后续相同请求命中返回缓存/409。失败不上锁（允许重试）。
        if commit_on_success:
            # 先检查是否已有成功记录（命中则直接返回缓存/409，避免重复执行）
            try:
                already = await redis.get(lock_key)
            except Exception:  # noqa: BLE001
                already = None
            if already:
                return await _handle_duplicate(redis, resp_key)

            # 执行 handler（失败直接抛出，不上锁，允许重试）
            result = await _call_func(func, *args, **kwargs)

            # 成功后写入幂等键 + 缓存响应
            try:
                await redis.set(lock_key, "1", ex=expire_seconds, nx=True)
            except Exception:  # noqa: BLE001 - Redis 异常不影响已成功的结果
                logger.debug("idempotent: commit_on_success 写键异常", exc_info=True)
            await _maybe_cache_response(redis, resp_key, result, expire_seconds)
            return result

        # ── 默认：请求时幂等（先抢锁）──
        # ── 获取锁 ──
        try:
            acquired = await redis.set(lock_key, "1", ex=expire_seconds, nx=True)
        except Exception:  # noqa: BLE001 - Redis 异常不阻塞请求
            logger.warning("idempotent: 获取锁异常，fail-open", extra={"path": req.url.path}, exc_info=True)
            return await _call_func(func, *args, **kwargs)

        if not acquired:
            # 重复请求：优先返回缓存响应，否则 409
            return await _handle_duplicate(redis, resp_key)

        # ── 首次请求：执行 handler ──
        try:
            result = await _call_func(func, *args, **kwargs)
        except Exception:
            # 处理失败：释放锁允许重试，不缓存
            await _safe_delete(redis, lock_key)
            raise

        # 缓存成功响应（可序列化且未超限时）
        await _maybe_cache_response(redis, resp_key, result, expire_seconds)
        return result

    wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
    return wrapper


async def _call_func(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """调用原函数，兼容 async / sync handler。"""
    # 移除装饰器注入的内部参数，避免透传给原函数
    kwargs.pop("_idem_request", None)
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return func(*args, **kwargs)


async def _handle_duplicate(redis: RedisManager, resp_key: str) -> Any:
    """重复请求处理：命中缓存返回首次响应，否则 409。"""
    cached = await _safe_get(redis, resp_key)
    if cached:
        try:
            payload = json.loads(cached)
            status = int(payload.get("code", 200))
            return JSONResponse(status_code=status, content=payload.get("body"))
        except Exception:  # noqa: BLE001
            pass
    return JSONResponse(
        status_code=409,
        content=_conflict_body(),
        headers={"X-Idempotency-Status": "in-progress"},
    )


async def _maybe_cache_response(
    redis: RedisManager, resp_key: str, result: Any, ttl: int
) -> None:
    serialized = _serialize_result(result)
    if serialized is None:
        return  # 不可序列化（如 StreamingResponse）→ 不缓存，重复请求走 409
    status, body = serialized
    try:
        encoded = json.dumps({"code": status, "body": body}, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    if len(encoded.encode("utf-8")) > _MAX_CACHE_BYTES:
        return  # 超限不缓存
    try:
        await redis.set(resp_key, encoded, ex=ttl)
    except Exception:  # noqa: BLE001
        logger.debug("idempotent: 缓存响应失败，忽略", exc_info=True)


async def _safe_get(redis: RedisManager, key: str) -> Optional[str]:
    try:
        return await redis.get(key)
    except Exception:  # noqa: BLE001
        return None


async def _safe_delete(redis: RedisManager, key: str) -> None:
    try:
        await redis.delete(key)
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "idempotent",
    "configure_idempotency",
]
