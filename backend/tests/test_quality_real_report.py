"""Real shared report: parsing and scoring must survive real-world markdown."""
from __future__ import annotations

import unittest
from pathlib import Path

from quality import checks, engine, parse

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "quality_report_real.md"


class RealReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = FIXTURE.read_text(encoding="utf-8")
        # 把真实报告自带的来源列表当作"检索结果"，验证真实格式的解析与打分
        cls.citations = parse.extract_citations(cls.report)
        cls.sources = parse.merge_sources([
            parse.Source(title=item.text or "来源", url=item.url,
                         normalized=item.normalized, kind="web")
            for item in cls.citations if not item.is_local
        ])

    def test_report_is_split_into_many_sections(self):
        sections = parse.split_sections(self.report)
        self.assertGreaterEqual(len(sections), 6)
        self.assertTrue(all(section.heading for section in sections[1:]))

    def test_real_report_has_many_citations(self):
        self.assertGreaterEqual(len(self.citations), 20)
        self.assertTrue(any(citation.form == "bullet" for citation in self.citations))

    def test_audit_runs_on_real_report(self):
        result = engine.audit(self.report, self.sources, [], set())
        self.assertTrue(result["report_available"])
        self.assertGreaterEqual(result["metrics"]["cited_unique"], 15)
        self.assertIn(result["score"], range(0, 101))
        self.assertIn(result["grade"], {"A", "B", "C", "D"})
        self.assertGreaterEqual(len(result["sources"]), 15)
        # 真实报告的来源只堆在文末，应给出"全文无行内引用"这一条明确结论
        self.assertEqual(result["metrics"]["inline_citations"], 0)
        self.assertIn("no_inline_citations", {issue["type"] for issue in result["issues"]})
        self.assertGreaterEqual(len(result["citations"]), 20)
        self.assertTrue(all(citation["section"] for citation in result["citations"]))

    def test_citations_from_report_are_matched_to_sources(self):
        issues, stats = checks.citation_issues(self.citations, self.sources, set())
        self.assertEqual(stats.unverified, 0)
        self.assertNotIn("unverified_url", {issue.type for issue in issues})

    def test_quality_report_render_contains_real_findings(self):
        from quality import render

        result = engine.audit(self.report, self.sources, [], set())
        markdown = render.render_quality_report(result, topic="多模态大模型 2025 关键突破")
        self.assertIn("# 报告质检单", markdown)
        self.assertIn("## 二、体检指标", markdown)
        self.assertIn("问题清单", markdown)


if __name__ == "__main__":
    unittest.main()
