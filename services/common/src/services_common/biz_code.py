"""业务码编码模块 - 提供统一的 biz_code 生成与解析规则

biz_code 为 8 位整数，结构如下：

    biz_code = 1 SS DDD EEE
               │ │  │   └─ 3位 业务错误序号 (001-999, 0=成功)
               │ │  └──── 3位 业务大类 (BizCategory 枚举值)
               │ └──────── 2位 服务编号 (00-89, 00=模板/公共占位)
               └────────── 固定前缀 1（保证始终 8 位数）

固定前缀 1 确保所有 biz_code 都是完整的 8 位整数（10,000,000 ~ 99,099,999），
避免 service_code 较小时因整数前导零丢失导致位数不足。

设计原则：
  - services_common 只提供编码规则和工具函数，不含任何服务枚举
  - 各服务在自己的 foundation/biz_code.py 中声明 SERVICE_CODE 和 BizCode
  - 服务编号全局唯一，通过 service.metadata 中的 service_code 字段管理
  - 新增服务时由 generate-service 脚本自动分配并检测冲突

示例：
    # account-service 中声明
    SERVICE_CODE = 1  # account-service 全局唯一编号
    class BizCode(IntEnum):
        SUCCESS             = make_biz_code(SERVICE_CODE, BizCategory.SUCCESS, 0)        # 11000000
        AUTH_PASSWORD_ERROR = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 1)           # 11002001
        USER_NOT_FOUND      = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 1)      # 11003001
"""

from enum import IntEnum

# 固定基座，保证 biz_code 始终为 8 位整数
_BIZ_CODE_BASE = 10_000_000


class BizCategory(IntEnum):
    """业务大类 - 所有服务共用统一语义

    每个服务按此分类定义自己的业务码序号，保证跨服务可读性。
    """

    SUCCESS = 0          # 通用成功
    VALIDATION = 1       # 参数校验类：必填缺失、格式错误、枚举非法
    AUTH = 2             # 认证授权类：未登录、token失效、无权限
    NOT_FOUND = 3        # 资源不存在类：实体未找到
    CONFLICT = 4         # 资源冲突类：重复创建、状态冲突
    QUOTA = 5            # 配额/限额类：余额不足、次数用尽、限流
    BUSINESS_RULE = 6    # 业务规则类：领域校验不通过，如订单状态不允许
    EXTERNAL = 7         # 外部依赖类：下游服务调用失败、第三方API异常
    CONSISTENCY = 8      # 数据一致性类：并发冲突、版本号过期
    CONTENT_MEDIA = 9    # 媒体/内容类：内容审核不通过、格式不支持
    PAYMENT_TXN = 10     # 支付/交易类：支付失败、退款异常
    LLM_AI = 11          # LLM/AI类：模型超时、内容生成失败
    SYSTEM = 99          # 系统内部错误：未分类异常兜底


def make_biz_code(service_code: int, category: BizCategory, seq: int) -> int:
    """组装业务码（始终返回 8 位整数）

    Args:
        service_code: 服务编号 (0-89)，0 预留给模板/公共占位，实际服务使用 1-89
        category: 业务大类
        seq: 业务序号 (0-999)，0 通常表示成功

    Returns:
        8 位整数业务码，如 11002001

    Examples:
        >>> make_biz_code(0, BizCategory.BUSINESS_RULE, 2)
        10006002
        >>> make_biz_code(1, BizCategory.AUTH, 1)
        11002001
        >>> make_biz_code(15, BizCategory.SUCCESS, 0)
        25000000
    """
    if not (0 <= service_code <= 89):
        raise ValueError(f"service_code 必须在 0-89 之间（0 预留给模板/公共），当前: {service_code}")
    if not (0 <= seq <= 999):
        raise ValueError(f"seq 必须在 0-999 之间，当前: {seq}")
    return _BIZ_CODE_BASE + service_code * 1_000_000 + int(category) * 1_000 + seq


def parse_biz_code(code: int) -> tuple[int, BizCategory, int]:
    """解析业务码为 (service_code, category, seq)

    Args:
        code: 8 位整数业务码

    Returns:
        (service_code, BizCategory, seq) 三元组

    Examples:
        >>> parse_biz_code(11002001)
        (1, <BizCategory.AUTH: 2>, 1)
        >>> parse_biz_code(10006002)
        (0, <BizCategory.BUSINESS_RULE: 6>, 2)
    """
    value = code - _BIZ_CODE_BASE
    service_code = value // 1_000_000
    category = BizCategory((value // 1_000) % 1_000)
    seq = value % 1_000
    return service_code, category, seq