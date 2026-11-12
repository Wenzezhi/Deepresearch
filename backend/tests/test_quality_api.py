"""The quality API is read-only and must not depend on the research pipeline."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import quality_api
from storage import Store

REPORT = """# 测试研究报告

## 一、背景

多模态模型发展迅速，见 [MMMU-Pro 榜单](https://llm-stats.com/benchmarks/mmmu-pro)。

## 二、结论

LoRA 在低资源场景下更省显存，见 https://arxiv.org/abs/2106.09685 。

## 三、局限与风险

样本规模有限，结论仅适用于小团队场景。
"""

SOURCES = (
    "* MMMU-Pro Leaderboard : https://llm-stats.com/benchmarks/mmmu-pro\n"
    "* STORM 论文 : https://research.nvidia.com/labs/lpr/storm\n"
    "* OSWorld : https://osworld-v1.xlang.ai\n"
)


class FakeJobs:
    def __init__(self, tasks=None):
        self.tasks = tasks or []

    def snapshot(self, run_id):  # noqa: ARG002
        return self.tasks


class QualityApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = Store(Path(self.tmp) / "research.sqlite3")
        self.run_id = "run-quality-1"
        self.store.create_run(
            topic="测试主题",
            profile={"id": "p1", "name": "fake"},
            search_api="duckduckgo",
            identifier=self.run_id,
        )
        self.store.append_events(self.run_id, [
            {"type": "status", "message": "初始化研究流程"},
            {"type": "sources", "task_id": 1, "latest_sources": SOURCES},
            {"type": "final_report", "report": REPORT},
        ])
        self.other_run = "run-quality-2"
        self.store.create_run(
            topic="没有报告的研究",
            profile={"id": "p1", "name": "fake"},
            search_api="duckduckgo",
            identifier=self.other_run,
        )
        self.store.append_events(self.other_run, [{"type": "status", "message": "开始"}])

        app = FastAPI()
        app.include_router(quality_api.router(self.store, FakeJobs()))
        self.client = TestClient(app)

    def test_audit_returns_metrics_and_sources(self):
        response = self.client.get(f"/quality/audit/{self.run_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["report_available"])
        self.assertIn(payload["grade"], {"A", "B", "C", "D"})
        metrics = payload["metrics"]
        self.assertGreaterEqual(metrics["cited_links"], 2)
        # 报告引用了 2 条：一条来自检索来源，一条不在来源里（应被判为未核验）
        self.assertEqual(metrics["verified"], 1)
        self.assertEqual(metrics["unverified"], 1)
        self.assertEqual(len(payload["sources"]), 4)
        self.assertTrue(all("type" in issue for issue in payload["issues"]))

    def test_unknown_run_returns_404(self):
        response = self.client.get("/quality/audit/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_report_without_final_report_is_flagged(self):
        response = self.client.get(f"/quality/audit/{self.other_run}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["report_available"])

    def test_quality_report_markdown(self):
        response = self.client.post(
            "/quality/report",
            json={"run_id": self.run_id, "style": "plain"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("# 报告质检单", payload["markdown"])
        self.assertIn("## 参考文献", payload["references_markdown"])
        self.assertIn("[1]", payload["references_markdown"])
        self.assertIsInstance(payload["score"], int)

    def test_invalid_style_returns_422(self):
        response = self.client.post(
            "/quality/report",
            json={"run_id": self.run_id, "style": "chicago"},
        )
        self.assertEqual(response.status_code, 422)

    def test_audit_is_idempotent_except_timestamp(self):
        first = self.client.get(f"/quality/audit/{self.run_id}").json()
        second = self.client.get(f"/quality/audit/{self.run_id}").json()
        first.pop("generated_at")
        second.pop("generated_at")
        self.assertEqual(first, second)

    def test_audit_does_not_write_events(self):
        before = len(self.store.events(self.run_id))
        self.client.get(f"/quality/audit/{self.run_id}")
        self.client.post("/quality/report", json={"run_id": self.run_id})
        after = len(self.store.events(self.run_id))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
