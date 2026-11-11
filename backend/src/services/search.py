"""Bounded search retries with explicit failures and configured fallbacks."""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Optional, Tuple

from hello_agents.tools import SearchTool
from config import Configuration
from utils import deduplicate_and_format_sources, format_sources, get_config_value

logger = logging.getLogger(__name__)
MAX_TOKENS_PER_SOURCE = 2000
_GLOBAL_SEARCH_TOOL = SearchTool(backend="hybrid")


class SearchFailure(RuntimeError):
    """A search service failed; this is not a confirmed empty result."""


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    for key, value in os.environ.items():
        if value and any(part in key.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", text)
    return text[:500]


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, (ValueError, TypeError, ImportError)):
        return False
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (400, 401, 403, 404, 422):
        return False
    text = str(exc).lower()
    return not any(term in text for term in (
        "unauthorized", "invalid api key", "api key required", "api key is required",
        "api key not", "api_key not", "forbidden", "未配置", "未设置", "未安装",
        "不支持", "unsupported", "401", "403",
    ))


def _fallback_ready(backend: str) -> bool:
    required = {"tavily": "TAVILY_API_KEY", "perplexity": "PERPLEXITY_API_KEY", "searxng": "SEARXNG_URL"}
    return backend in required and bool(os.getenv(required[backend], "").strip())


def dispatch_search(query: str, config: Configuration, loop_count: int
                    ) -> Tuple[dict[str, Any] | None, list[str], Optional[str], str]:
    primary = get_config_value(config.search_api)
    backends = [primary]
    notices: list[str] = []
    for backend in config.search_fallback_apis.split(","):
        backend = backend.strip().lower()
        if not backend or backend in backends:
            continue
        if _fallback_ready(backend):
            backends.append(backend)
        else:
            notices.append(f"备用搜索 {backend} 未配置必要凭证或地址，未启用。")

    failures: list[str] = []
    empty_payload = None
    for backend in backends:
        for attempt in range(1, config.search_max_attempts + 1):
            try:
                raw = _GLOBAL_SEARCH_TOOL.run({
                    "input": query, "backend": backend, "mode": "structured",
                    "fetch_full_page": config.fetch_full_page, "max_results": 5,
                    "max_tokens_per_source": MAX_TOKENS_PER_SOURCE, "loop_count": loop_count,
                })
                # A textual error from the tool must not masquerade as an empty search.
                if not isinstance(raw, dict):
                    raise SearchFailure(str(raw) if isinstance(raw, str) else "搜索服务返回了无效格式。")
                if raw.get("error"):
                    raise SearchFailure(str(raw["error"]))
                if not isinstance(raw.get("results"), list):
                    raise SearchFailure("搜索响应缺少 results 列表。")
                raw = dict(raw)
                label = str(raw.get("backend") or backend)
                raw_notices = raw.get("notices") or []
                if isinstance(raw_notices, str):
                    raw_notices = [raw_notices]
                notices.extend(_safe_error(SearchFailure(str(n))) for n in raw_notices)
                if not raw["results"]:
                    empty_payload = raw, label
                    notices.append(f"{backend} 正常返回，但此查询没有搜索结果。")
                    break
                if backend != primary:
                    notices.append(f"已切换到配置的备用搜索服务：{backend}。")
                raw["notices"] = notices
                logger.info("Search backend=%s attempts=%s results=%s", label, attempt, len(raw["results"]))
                return raw, notices, raw.get("answer"), label
            except Exception as exc:
                detail = _safe_error(exc)
                logger.warning("Search backend=%s attempt=%s/%s failed: %s", backend, attempt, config.search_max_attempts, detail)
                if attempt < config.search_max_attempts and _retryable(exc):
                    notices.append(f"{backend} 第 {attempt} 次搜索失败，正在重试。")
                    time.sleep(config.search_retry_delay * attempt)
                    continue
                if backend == "duckduckgo" and "no results found" in detail.lower():
                    detail = ("DuckDuckGo 未返回可解析的搜索结果；可能受到机器人验证或访问限制，"
                              "不能据此认定主题没有资料。请检查网络或配置备用搜索服务。")
                failure = f"{backend} 搜索失败（已尝试 {attempt} 次）：{detail}"
                failures.append(failure)
                notices.append(failure)
                break
    if empty_payload is not None:
        raw, label = empty_payload
        raw["notices"] = notices
        return raw, notices, raw.get("answer"), label
    raise SearchFailure("；".join(notices or failures) or "没有可用的搜索服务。")


def prepare_research_context(
    search_result: dict[str, Any] | None,
    answer_text: Optional[str],
    config: Configuration,
) -> tuple[str, str]:
    """Build structured context and source summary for downstream agents."""

    sources_summary = format_sources(search_result)
    context = deduplicate_and_format_sources(
        search_result or {"results": []},
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=config.fetch_full_page,
    )

    if answer_text:
        context = f"AI直接答案：\n{answer_text}\n\n{context}"

    return sources_summary, context
