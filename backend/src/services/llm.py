"""Model adapter: bounded output and safe response diagnostics for both modes."""
from __future__ import annotations

import logging
import re
import time
from openai import APIConnectionError, APIStatusError
from hello_agents import HelloAgentsLLM

logger = logging.getLogger(__name__)

# One shared budget per model request: initial attempt plus at most three retries.
MAX_MODEL_RETRIES = 3


class ModelOutputError(RuntimeError):
    """The model returned no usable answer or an incomplete answer."""


class EmptyModelOutputError(ModelOutputError):
    """A response arrived but contains no user-visible body."""


def require_text(text: str | None, stage: str) -> str:
    if not text or not text.strip():
        logger.error("Empty model output after cleaning: stage=%s", stage)
        raise ModelOutputError(f"{stage}失败：模型没有返回可用正文，请重试；若持续发生，请检查模型服务的响应内容。")
    return text.strip()


class ResearchLLM(HelloAgentsLLM):
    """Keep diagnostics local to each call because task summaries run concurrently."""

    def _create_client(self):
        client = super()._create_client()
        # Disable hidden SDK retries: network failures and empty bodies share our budget.
        client.max_retries = 0
        return client

    def _check_cancelled(self):
        if getattr(self, 'cancel_event', None) is not None and self.cancel_event.is_set():
            raise ModelOutputError('研究已暂停')

    def _request_options(self, kwargs, *, stream):
        self._check_cancelled()
        options = dict(kwargs)
        options.update(model=self.model, stream=stream)
        options.setdefault("temperature", self.temperature)
        options["max_tokens"] = options.get("max_tokens") or self.max_tokens or 8192
        return options

    def _validate_output(self, content, finish_reason, limit, mode, usage=None):
        if getattr(self, 'cancel_event', None) is not None and self.cancel_event.is_set():
            raise ModelOutputError('研究已暂停')
        # Never log prompts, generated text, reasoning text, or credentials.
        logger.info(
            "LLM response mode=%s model=%s max_tokens=%s finish_reason=%s content_chars=%s completion_tokens=%s",
            mode, self.model, limit, finish_reason, len(content),
            getattr(usage, "completion_tokens", None),
        )
        if finish_reason == "length":
            raise ModelOutputError(
                f"模型输出被截断（finish_reason=length，max_tokens={limit}），未将不完整内容作为结果。"
                "请提高 LLM_MAX_TOKENS 或缩短研究范围后重试。"
            )
        if finish_reason == "content_filter":
            raise ModelOutputError("模型服务拦截了本次输出（content_filter），请调整研究内容后重试。")
        visible = re.sub(r"<(think|thinking|reasoning|analysis)\b[^>]*>[\s\S]*?(?:</\1\s*>|$)", "", content, flags=re.I)
        visible = re.sub(r"</?final_answer>", "", visible, flags=re.I).strip()
        if not visible:
            raise EmptyModelOutputError("模型返回空正文（或仅包含推理内容），未生成可用答案。")
        if finish_reason is None:
            raise ModelOutputError("模型响应未正常结束，未将不完整内容作为结果，请重试。")
        require_text(content, "模型生成")

    @staticmethod
    def _retryable(exc):
        if isinstance(exc, (EmptyModelOutputError, APIConnectionError)):
            return True
        if isinstance(exc, APIStatusError):
            return exc.status_code in (408, 409, 429) or exc.status_code >= 500
        return False

    def _retry(self, exc, attempt):
        self._check_cancelled()
        if not self._retryable(exc):
            raise exc
        if attempt >= MAX_MODEL_RETRIES:
            if isinstance(exc, EmptyModelOutputError):
                raise EmptyModelOutputError(
                    f"模型返回空正文，已达到最多 {MAX_MODEL_RETRIES} 次重试（共 {attempt+1} 次请求），仍未获得可用答案。"
                ) from exc
            raise exc
        logger.warning("LLM retry model=%s retry=%s/%s reason=%s status=%s",
                       self.model, attempt+1, MAX_MODEL_RETRIES, type(exc).__name__,
                       getattr(exc, 'status_code', None))
        delay = min(0.5 * 2 ** attempt, 2)
        cancel = getattr(self, 'cancel_event', None)
        if cancel is not None:
            cancel.wait(delay)
        else:
            time.sleep(delay)
        self._check_cancelled()

    @staticmethod
    def _retry_messages(messages, empty_seen):
        # Do not append failed/hidden output, or mutate the agent's conversation history.
        if not empty_seen:
            return messages
        return [*messages, {"role": "user", "content":
            "上一次响应没有可用正文。请继续完成当前请求，将答案输出在正文 content 中，不要只返回推理内容。"
            "若仍需调用工具，请遵循原有工具调用格式。"}]

    def _response_diagnostics(self, message, attempt):
        # Log presence only. Never expose reasoning, tool arguments, prompts, or keys.
        logger.info("LLM response fields model=%s attempt=%s has_reasoning=%s has_tool_calls=%s",
                    self.model, attempt+1,
                    bool(getattr(message, 'reasoning_content', None) or getattr(message, 'reasoning', None)),
                    bool(getattr(message, 'tool_calls', None) or getattr(message, 'function_call', None)))

    def invoke(self, messages, **kwargs):
        empty_seen = False
        for attempt in range(MAX_MODEL_RETRIES + 1):
            options = self._request_options(kwargs, stream=False)
            try:
                response = self._client.chat.completions.create(
                    messages=self._retry_messages(messages, empty_seen), **options)
                choice = response.choices[0] if response.choices else None
                message = choice.message if choice else None
                content = (message.content or "") if message else ""
                self._response_diagnostics(message, attempt)
                self._validate_output(content, choice.finish_reason if choice else None,
                                      options["max_tokens"], "sync", getattr(response, "usage", None))
                return content
            except (ModelOutputError, APIConnectionError, APIStatusError) as exc:
                empty_seen = empty_seen or isinstance(exc, EmptyModelOutputError)
                self._retry(exc, attempt)

    def stream_invoke(self, messages, **kwargs):
        empty_seen = False
        for attempt in range(MAX_MODEL_RETRIES + 1):
            options = self._request_options(kwargs, stream=True)
            parts = []
            finish_reason = None
            usage = None
            response = None
            try:
                response = self._client.chat.completions.create(
                    messages=self._retry_messages(messages, empty_seen), **options)
                for chunk in response:
                    self._check_cancelled()
                    if getattr(chunk, "usage", None) is not None:
                        usage = chunk.usage
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.finish_reason is not None:
                        finish_reason = choice.finish_reason
                    content = choice.delta.content or ""
                    if content:
                        parts.append(content)
                        yield content
                self._validate_output("".join(parts), finish_reason, options["max_tokens"], "stream", usage)
                return
            except (ModelOutputError, APIConnectionError, APIStatusError) as exc:
                # Once text was emitted, replaying the request would duplicate partial text.
                if parts:
                    raise
                if response is not None:
                    response.close()
                    response = None
                empty_seen = empty_seen or isinstance(exc, EmptyModelOutputError)
                self._retry(exc, attempt)
            finally:
                if response is not None:
                    response.close()
