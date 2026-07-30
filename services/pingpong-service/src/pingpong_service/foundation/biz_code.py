"""PingPong 服务业务码定义

biz_code 为 8 位整数，结构: 1 SS DDD EEE
  1    = 固定前缀（保证始终 8 位数）
  SS   = 服务编号 (00-89)，由 generate-service 脚本分配并写入 service.metadata
  DDD  = 业务大类 (BizCategory 枚举值)
  EEE  = 业务序号 (001-999, 0=成功)

此文件是服务模板的一部分。generate-service 创建新服务时会将
SERVICE_CODE 的值替换为新服务实际分配到的服务编号。
"""

from enum import IntEnum

from services_common.biz_code import BizCategory, make_biz_code

# 服务编号 - 由 generate-service 脚本在创建服务时自动替换
# pingpong 是服务模板，使用 0 作为占位符（非实际服务编号）
SERVICE_CODE = 0


class BizCode(IntEnum):
    """PingPong 服务业务码枚举

    每个成员必须附带中文注释，描述具体的业务场景或问题。
    新增业务码时遵循以下规则：
      1. 按 BizCategory 大类分组，序号从 1 递增
      2. 注释格式：业务场景中文描述
    """

    # ── 通用成功 ──
    SUCCESS = make_biz_code(SERVICE_CODE, BizCategory.SUCCESS, 0)         # 请求处理成功

    # ── 参数校验类 ──
    VALIDATION_FAILED = make_biz_code(SERVICE_CODE, BizCategory.VALIDATION, 1)   # 请求参数校验不通过（必填缺失/格式错误）

    # ── 认证授权类 ──
    AUTH_PASSWORD_ERROR = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 1)       # 用户名或密码错误
    AUTH_TOKEN_INVALID = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 2)        # token 格式非法或无法解析
    AUTH_TOKEN_EXPIRED = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 3)        # token 已超过有效期
    AUTH_TOKEN_BLACKLISTED = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 4)    # token 已被主动注销/拉黑
    AUTH_FAILED = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 5)               # 登录流程中身份验证未通过
    AUTH_NO_PERMISSION = make_biz_code(SERVICE_CODE, BizCategory.AUTH, 6)        # 已认证但无权限访问该资源

    # ── 资源不存在类 ──
    PAP_NOT_FOUND = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 1)        # PingPong 记录不存在
    PONG_NOT_FOUND = make_biz_code(SERVICE_CODE, BizCategory.NOT_FOUND, 2)       # Pong 记录不存在

    # ── 资源冲突类 ──
    PAP_ALREADY_EXISTS = make_biz_code(SERVICE_CODE, BizCategory.CONFLICT, 1)    # PingPong 记录已存在（唯一约束冲突）
    PAP_DISABLED = make_biz_code(SERVICE_CODE, BizCategory.CONFLICT, 2)          # PingPong 记录已被禁用，操作不允许

    # ── 业务规则类 ──
    PASSWORD_TOO_WEAK = make_biz_code(SERVICE_CODE, BizCategory.BUSINESS_RULE, 1)  # 密码强度不足，不满足复杂度要求
    REGISTRATION_FAILED = make_biz_code(SERVICE_CODE, BizCategory.BUSINESS_RULE, 2)  # 注册流程失败（用户名占用等）
    PASSWORD_RESET_FAILED = make_biz_code(SERVICE_CODE, BizCategory.BUSINESS_RULE, 3)  # 密码重置失败（旧密码不匹配等）

    # ── 系统内部错误 ──
    INTERNAL_ERROR = make_biz_code(SERVICE_CODE, BizCategory.SYSTEM, 0)          # 服务内部未分类异常兜底