"""LLM Token 用量工具

统一 TokenUsage 数据结构 + 从各平台 LLM/API 响应中提取 token 用量 +
tiktoken 兜底估算。

支持的平台：
  - OpenAI 兼容（硅基流动/OpenRouter/GPT 等）：resp["usage"]
  - 后续扩展：Anthropic / Google Gemini / Cohere 等
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """单次 LLM/Embedding 调用的 token 用量记录"""

    stage: str                      # 阶段标识：knowledge_injection / video_understand / rag_embed / ...
    description: str = ""           # 人类可读描述
    model: str = ""                 # 模型名称
    provider: str = ""              # 供应商标识（base_url 域名，如 openrouter / siliconflow / zeroone01）
    prompt_tokens: int = 0          # 输入 token（含 system + user）
    completion_tokens: int = 0      # 输出 token（含 reasoning_tokens）
    reasoning_tokens: int = 0       # 推理思考 token（completion_tokens 的子集）
    total_tokens: int = 0           # 总 token = prompt_tokens + completion_tokens

    def to_dict(self) -> dict:
        d = asdict(self)
        # 兼容外部期望字段名：input_tokens = prompt_tokens
        d["input_tokens"] = self.prompt_tokens
        d["output_tokens"] = self.completion_tokens
        d["reasoning_tokens"] = self.reasoning_tokens
        return d

    @classmethod
    def from_dict(cls, d: dict) -> TokenUsage:
        return cls(
            stage=d.get("stage", ""),
            description=d.get("description", ""),
            model=d.get("model", ""),
            provider=d.get("provider", ""),
            prompt_tokens=d.get("prompt_tokens") or d.get("input_tokens", 0),
            completion_tokens=d.get("completion_tokens") or d.get("output_tokens", 0),
            reasoning_tokens=d.get("reasoning_tokens", 0),
            total_tokens=d.get("total_tokens", 0),
        )


def extract_provider_from_url(base_url: str) -> str:
    """从 base_url 提取干净的域名作为 provider 标识。"""
    if not base_url:
        return ""
    try:
        from urllib.parse import urlparse
        host = urlparse(base_url).hostname or ""
        parts = host.split(".")
        if len(parts) >= 2:
            name = parts[0] if parts[0] != "api" else parts[-2] if len(parts) >= 3 else parts[1]
            return name
        return host
    except Exception:
        return ""


def extract_usage_from_response(
    response_data: dict,
    *,
    stage: str,
    description: str = "",
    model: str = "",
    provider: str = "",
) -> TokenUsage | None:
    """从 LLM/API JSON 响应中提取 token usage。

    支持的响应格式：
      - OpenAI 兼容: {"usage": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}}
      - Anthropic:   {"usage": {"input_tokens": N, "output_tokens": N}}
      - 其他:        尝试 usage.input_tokens / usage.output_tokens
    """
    usage = response_data.get("usage")
    if not usage or not isinstance(usage, dict):
        return None

    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or 0
    )
    completion_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or 0
    )
    total_tokens = (
        usage.get("total_tokens")
        or (prompt_tokens + completion_tokens)
    )

    if not total_tokens:
        return None

    # reasoning_tokens: completion_tokens 的子集，从 completion_tokens_details 提取
    completion_details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = (
        completion_details.get("reasoning_tokens")
        or usage.get("reasoning_tokens")  # 部分平台直接平铺
        or 0
    )

    return TokenUsage(
        stage=stage,
        description=description,
        model=model or response_data.get("model", ""),
        provider=provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
    )


def estimate_usage_tiktoken(
    messages: list[dict] | str,
    *,
    stage: str,
    description: str = "",
    model: str = "",
    provider: str = "",
    completion_text: str = "",
) -> TokenUsage:
    """使用 tiktoken 兜底估算 token 用量。"""
    prompt_tokens = _count_tokens(messages, model=model)
    completion_tokens = _count_tokens(completion_text, model=model) if completion_text else 0
    return TokenUsage(
        stage=stage,
        description=description,
        model=model,
        provider=provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def _count_tokens(text_or_messages: str | list[dict], *, model: str = "") -> int:
    """估算 token 数量，优先用 tiktoken，失败时按字符数粗估。"""
    if not text_or_messages:
        return 0

    # 消息列表 → 拼接文本
    if isinstance(text_or_messages, list):
        parts: list[str] = []
        for msg in text_or_messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            parts.append(str(block.get("text", "")))
            elif isinstance(msg, str):
                parts.append(msg)
        text = " ".join(parts)
    else:
        text = text_or_messages

    # 尝试 tiktoken
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model(model) if model else tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        pass

    # 兜底：中文按 1 字 ≈ 1.5 token，英文按 4 字符 ≈ 1 token
    chinese_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_count = len(text) - chinese_count
    return int(chinese_count * 1.5 + other_count / 4)


def merge_usage_tokens(
    existing: list[dict],
    new_entries: list[dict],
) -> list[dict]:
    """合并 usage_tokens 列表，同 stage 的条目累加 token 数。

    用于 DB 中 usage_tokens JSON 列的累加更新，避免重复记录。
    """
    by_stage: dict[str, dict] = {}
    for entry in existing:
        stage = entry.get("stage", "")
        by_stage[stage] = dict(entry)

    for entry in new_entries:
        stage = entry.get("stage", "")
        if stage in by_stage:
            cur = by_stage[stage]
            cur["prompt_tokens"] = cur.get("prompt_tokens", 0) + entry.get("prompt_tokens", 0)
            cur["completion_tokens"] = cur.get("completion_tokens", 0) + entry.get("completion_tokens", 0)
            cur["reasoning_tokens"] = cur.get("reasoning_tokens", 0) + entry.get("reasoning_tokens", 0)
            cur["total_tokens"] = cur.get("total_tokens", 0) + entry.get("total_tokens", 0)
            cur["input_tokens"] = cur["prompt_tokens"]
            cur["output_tokens"] = cur["completion_tokens"]
        else:
            by_stage[stage] = dict(entry)

    return list(by_stage.values())