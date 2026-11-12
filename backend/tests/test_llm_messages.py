"""严格 OpenAI 兼容服务（如 Moonshot）不接受空 assistant 消息，必须发送前清洗。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.llm import ModelOutputError, ResearchLLM


def make_llm():
    llm = object.__new__(ResearchLLM)
    llm.model = "test-model"
    llm.max_tokens = 1024
    llm.temperature = 1
    llm._client = Mock()
    return llm


def ok_response(content="answer"):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=None, reasoning_content=None),
            finish_reason="stop",
        )],
        usage=None,
    )


class SanitizeMessagesTests(unittest.TestCase):
    def test_empty_assistant_turn_is_dropped(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "工具执行结果"},
        ]
        cleaned = ResearchLLM._sanitize_messages(messages)
        self.assertEqual([m["role"] for m in cleaned], ["system", "user", "user"])

    def test_empty_assistant_with_tool_calls_keeps_placeholder(self):
        messages = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "1", "type": "function"}],
        }]
        cleaned = ResearchLLM._sanitize_messages(messages)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["content"], "(调用工具)")
        self.assertIn("tool_calls", cleaned[0])

    def test_non_empty_assistant_untouched(self):
        messages = [{"role": "assistant", "content": "已有回答"}]
        cleand = ResearchLLM._sanitize_messages(messages)
        self.assertEqual(cleand, messages)

    def test_does_not_mutate_caller_list(self):
        messages = [{"role": "assistant", "content": ""}]
        ResearchLLM._sanitize_messages(messages)
        self.assertEqual(messages, [{"role": "assistant", "content": ""}])

    def test_non_dict_messages_are_preserved(self):
        marker = object()
        cleaned = ResearchLLM._sanitize_messages([marker])
        self.assertEqual(cleaned, [marker])


class InvokeSanitizesTests(unittest.TestCase):
    def test_invoke_sends_sanitized_messages(self):
        llm = make_llm()
        llm._client.chat.completions.create.return_value = ok_response()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "工具执行结果"},
        ]
        answer = llm.invoke(messages)
        self.assertEqual(answer, "answer")
        sent = llm._client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual([m["role"] for m in sent], ["system", "user", "user"])

    def test_stream_sends_sanitized_messages(self):
        llm = make_llm()

        class Stream:
            def __iter__(self):
                yield SimpleNamespace(
                    choices=[SimpleNamespace(
                        delta=SimpleNamespace(content="ok"),
                        finish_reason="stop",
                    )],
                    usage=None,
                )

            def close(self):
                return None

        llm._client.chat.completions.create.return_value = Stream()
        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": ""},
        ]
        chunks = list(llm.stream_invoke(messages))
        self.assertEqual("".join(chunks), "ok")
        sent = llm._client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual([m["role"] for m in sent], ["user"])


if __name__ == "__main__":
    unittest.main()
