import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from config import Configuration
from agent import DeepResearchAgent
from models import SummaryState
from services.llm import ResearchLLM, ModelOutputError
from services.reporter import ReportingService
from services.summarizer import SummarizationService
import test_search_resilience as fixtures
from test_search_resilience import result


class Stream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False
    def __iter__(self):
        return iter(self.chunks)
    def close(self):
        self.closed = True


def chunk(content=None, reason=None):
    return NS(choices=[NS(delta=NS(content=content), finish_reason=reason)], usage=None)


class ModelTests(unittest.TestCase):
    def llm(self):
        llm = object.__new__(ResearchLLM)
        llm.model = "test-model"
        llm.max_tokens = 8192
        llm.temperature = 0
        llm._client = Mock()
        return llm

    def test_config_budget_reaches_model(self):
        with patch.dict(os.environ, {"LLM_MAX_TOKENS": "4096"}):
            config = Configuration.from_env()
        agent = object.__new__(DeepResearchAgent)
        agent.config = config
        with patch("agent.ResearchLLM") as constructor:
            agent._init_llm()
        self.assertEqual(constructor.call_args.kwargs["max_tokens"], 4096)
        with self.assertRaises(ValueError):
            Configuration(llm_max_tokens=0)

    def test_sync_output_and_safe_diagnostics(self):
        llm = self.llm()
        llm._client.chat.completions.create.return_value = NS(
            choices=[NS(message=NS(content="private answer"), finish_reason="stop")],
            usage=NS(completion_tokens=30))
        with self.assertLogs("services.llm", level="INFO") as logs:
            self.assertEqual(llm.invoke([{"role": "user", "content": "private prompt"}], max_tokens=None), "private answer")
        self.assertEqual(llm._client.chat.completions.create.call_args.kwargs["max_tokens"], 8192)
        self.assertIn("completion_tokens=30", str(logs.output))
        self.assertNotIn("private", str(logs.output))

    def test_empty_and_truncated_sync_fail(self):
        llm = self.llm()
        for text, reason in [("", "stop"), ("", "length"), ("partial", "length")]:
            with self.subTest(text=text, reason=reason):
                llm._client.chat.completions.create.return_value = NS(
                    choices=[NS(message=NS(content=text), finish_reason=reason)], usage=None)
                with self.assertRaises(ModelOutputError):
                    llm.invoke([])

    def test_stream_handles_usage_only_chunks(self):
        llm = self.llm()
        response = Stream([chunk("Hello"), chunk(" world", "stop"), NS(choices=[], usage=NS(completion_tokens=3))])
        llm._client.chat.completions.create.return_value = response
        self.assertEqual("".join(llm.stream_invoke([])), "Hello world")
        self.assertTrue(response.closed)
        self.assertEqual(llm._client.chat.completions.create.call_args.kwargs["max_tokens"], 8192)

    def test_empty_truncated_and_incomplete_stream_fail(self):
        llm = self.llm()
        for chunks in [[chunk(None, "stop")], [chunk("partial", "length")], [chunk("partial")]]:
            with self.subTest(chunks=chunks):
                response = Stream(chunks)
                llm._client.chat.completions.create.return_value = response
                with self.assertRaises(ModelOutputError):
                    list(llm.stream_invoke([]))
                self.assertTrue(response.closed)

    def test_cleaned_report_and_summary_cannot_be_empty(self):
        agent = Mock()
        agent.run.return_value = "<think>internal</think>"
        state = SummaryState(research_topic="test")
        with self.assertRaisesRegex(ModelOutputError, "最终报告"):
            ReportingService(agent, Configuration()).generate_report(state)
        task = fixtures.WorkflowTests().task()
        with self.assertRaisesRegex(ModelOutputError, "任务总结"):
            SummarizationService(lambda: agent, Configuration()).summarize_task(state, task, "context")
        self.assertEqual(agent.clear_history.call_count, 2)

    @patch("agent.dispatch_search", return_value=(result(), [], None, "tavily"))
    def test_empty_summary_fails_task_and_blocks_report(self, _):
        fixture = fixtures.WorkflowTests()
        task = fixture.task()
        agent = fixture.make_agent([task])
        agent.summarizer.stream_task_summary = lambda *a: (iter([]), lambda: "")
        events = list(agent.run_stream("test"))
        self.assertEqual(task.status, "failed")
        self.assertIn("任务总结", task.error)
        self.assertFalse(any(e.get("status") == "completed" for e in events))
        agent.reporting.generate_report.assert_not_called()

    @patch("agent.dispatch_search", return_value=(result(), [], None, "tavily"))
    def test_report_failure_emits_error_not_report_or_note(self, _):
        fixture = fixtures.WorkflowTests()
        agent = fixture.make_agent([fixture.task()])
        agent.reporting.generate_report.side_effect = ModelOutputError("最终报告失败：正文为空")
        agent._persist_final_report = Mock()
        events = list(agent.run_stream("test"))
        self.assertTrue(any(e["type"] == "error" and "正文为空" in e["detail"] for e in events))
        self.assertFalse(any(e["type"] == "final_report" for e in events))
        self.assertEqual(events[-1]["type"], "done")
        agent._persist_final_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
