import os
import sys
import unittest
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from config import Configuration
from services import search
from agent import DeepResearchAgent
from models import TodoItem


def result(backend="duckduckgo"):
    return {"backend": backend, "results": [{"title": "Python", "url": "https://www.python.org/", "content": "Python language"}]}


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.config = Configuration(search_retry_delay=0)
        self.tool = patch.object(search._GLOBAL_SEARCH_TOOL, "run").start()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()

    def test_success_needs_one_call(self):
        self.tool.return_value = result()
        payload, _, _, _ = search.dispatch_search("Python", self.config, 0)
        self.assertTrue(payload["results"])
        self.assertEqual(self.tool.call_count, 1)

    def test_timeout_retry_can_recover(self):
        self.tool.side_effect = [TimeoutError("timed out"), result()]
        _, notices, _, _ = search.dispatch_search("Python", self.config, 0)
        self.assertEqual(self.tool.call_count, 2)
        self.assertTrue(any("重试" in n for n in notices))

    def test_ambiguous_ddg_exception_remains_failure(self):
        self.tool.side_effect = RuntimeError("DuckDuckGo 搜索失败: No results found.")
        with self.assertRaisesRegex(search.SearchFailure, "机器人验证"):
            search.dispatch_search("Python", self.config, 0)
        self.assertEqual(self.tool.call_count, 2)

    def test_normal_empty_is_not_retried_or_failed(self):
        self.tool.return_value = {"results": []}
        payload, notices, _, _ = search.dispatch_search("rare query", self.config, 0)
        self.assertEqual(payload["results"], [])
        self.assertEqual(self.tool.call_count, 1)
        self.assertTrue(any("没有搜索结果" in n for n in notices))

    def test_auth_error_not_retried(self):
        self.tool.side_effect = RuntimeError("401 Unauthorized")
        with self.assertRaises(search.SearchFailure):
            search.dispatch_search("Python", self.config, 0)
        self.assertEqual(self.tool.call_count, 1)

    def test_unconfigured_fallback_not_called(self):
        self.config.search_fallback_apis = "tavily,searxng"
        self.tool.side_effect = TimeoutError("timed out")
        with self.assertRaisesRegex(search.SearchFailure, "未配置"):
            search.dispatch_search("Python", self.config, 0)
        self.assertTrue(all(c.args[0]["backend"] == "duckduckgo" for c in self.tool.call_args_list))

    def test_configured_fallback_is_used(self):
        self.config.search_fallback_apis = "tavily"
        os.environ["TAVILY_API_KEY"] = "test-secret"
        self.tool.side_effect = [TimeoutError(), TimeoutError(), result("tavily")]
        _, notices, _, backend = search.dispatch_search("Python", self.config, 0)
        self.assertEqual(backend, "tavily")
        self.assertEqual(self.tool.call_args.args[0]["backend"], "tavily")
        self.assertTrue(any("已切换" in n for n in notices))

    def test_normal_empty_can_use_fallback(self):
        self.config.search_fallback_apis = "tavily"
        os.environ["TAVILY_API_KEY"] = "test-secret"
        self.tool.side_effect = [{"results": []}, result("tavily")]
        self.assertEqual(search.dispatch_search("Python", self.config, 0)[3], "tavily")

    def test_text_error_not_misreported_as_empty(self):
        self.tool.return_value = "API key required"
        with self.assertRaises(search.SearchFailure):
            search.dispatch_search("Python", self.config, 0)
        self.assertEqual(self.tool.call_count, 1)

    def test_secrets_removed_from_errors(self):
        os.environ["TAVILY_API_KEY"] = "a-private-test-value"
        self.tool.side_effect = RuntimeError("401 a-private-test-value sk-testkey123")
        with self.assertRaises(search.SearchFailure) as error:
            search.dispatch_search("Python", self.config, 0)
        self.assertNotIn("a-private-test-value", str(error.exception))
        self.assertNotIn("sk-testkey123", str(error.exception))


class WorkflowTests(unittest.TestCase):
    def make_agent(self, tasks):
        agent = object.__new__(DeepResearchAgent)
        agent.config = Configuration(fetch_full_page=False)
        agent.planner = SimpleNamespace(plan_todo_list=lambda state: tasks)
        agent._state_lock = Lock()
        agent._drain_tool_events = lambda *args, **kwargs: []
        agent._set_tool_event_sink = lambda sink: None
        agent._persist_final_report = lambda *args: None
        agent.reporting = Mock()
        agent.reporting.generate_report.return_value = "Report with sources"
        def summarize(*args):
            return iter(["Verified summary"]), lambda: "Verified summary"
        agent.summarizer = SimpleNamespace(stream_task_summary=summarize, summarize_task=lambda *args: "Verified summary")
        return agent

    def task(self, task_id=1):
        return TodoItem(id=task_id, title="test", intent="test", query=str(task_id))

    @patch("agent.dispatch_search", side_effect=search.SearchFailure("Search timed out"))
    def test_failed_state_and_detail_reach_frontend(self, _):
        task = self.task()
        agent = self.make_agent([task])
        events = list(agent.run_stream("test"))
        failure = next(e for e in events if e.get("status") == "failed")
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.error, failure["detail"])
        self.assertIn(task.error, task.notices)
        self.assertTrue(any(e["type"] == "error" for e in events))
        self.assertFalse(any(e["type"] == "final_report" for e in events))
        agent.reporting.generate_report.assert_not_called()

    @patch("agent.dispatch_search", return_value=({"results": []}, [], None, "duckduckgo"))
    def test_empty_task_skipped_without_report(self, _):
        task = self.task()
        agent = self.make_agent([task])
        events = list(agent.run_stream("test"))
        self.assertEqual(task.status, "skipped")
        self.assertTrue(any(e.get("status") == "skipped" and e.get("detail") for e in events))
        agent.reporting.generate_report.assert_not_called()

    @patch("agent.dispatch_search")
    def test_one_failure_does_not_stop_other_task(self, dispatch):
        def run(query, *_):
            if query == "1": raise search.SearchFailure("Search timed out")
            return result(), [], None, "duckduckgo"
        dispatch.side_effect = run
        tasks = [self.task(1), self.task(2)]
        agent = self.make_agent(tasks)
        events = list(agent.run_stream("test"))
        self.assertEqual([t.status for t in tasks], ["failed", "completed"])
        self.assertTrue(any(e["type"] == "sources" for e in events))
        self.assertTrue(any(e["type"] == "final_report" for e in events))
        state = agent.reporting.generate_report.call_args.args[0]
        self.assertEqual(state.todo_items[0].error, "Search timed out")

    @patch("agent.dispatch_search", return_value=(result(), [], None, "duckduckgo"))
    def test_nonstream_endpoint_really_executes_search(self, dispatch):
        task = self.task()
        output = self.make_agent([task]).run("test")
        dispatch.assert_called_once()
        self.assertEqual(task.status, "completed")
        self.assertEqual(output.report_markdown, "Report with sources")


if __name__ == "__main__":
    unittest.main()
