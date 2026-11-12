"""Checks must be precise: false positives are as harmful as misses."""
from __future__ import annotations

import unittest

from quality import checks, engine, parse

SOURCES_TEXT = (
    "* MMMU-Pro Leaderboard : https://llm-stats.com/benchmarks/mmmu-pro\n"
    "* STORM 论文 : https://research.nvidia.com/labs/lpr/storm\n"
    "* OSWorld : https://osworld-v1.xlang.ai\n"
)


def build(report: str, sources_text: str = SOURCES_TEXT, known: set[str] | None = None):
    sources = parse.merge_sources(parse.parse_sources(sources_text))
    citations = parse.extract_citations(report)
    sections = parse.split_sections(report)
    return sources, citations, sections


class CitationCheckTests(unittest.TestCase):
    def test_unverified_link_is_reported(self):
        report = "# 报告\n\n## 一、结论\n\n该结论来自 [某来源](https://fake.example.com/x)。\n"
        sources, citations, _ = build(report)
        issues, stats = checks.citation_issues(citations, sources, set())
        types = {issue.type for issue in issues}
        self.assertIn("unverified_url", types)
        self.assertEqual(stats.unverified, 1)
        self.assertEqual(stats.verified, 0)

    def test_verified_link_passes(self):
        report = "# 报告\n\n## 一、结论\n\n见 [MMMU](https://llm-stats.com/benchmarks/mmmu-pro)。\n"
        sources, citations, _ = build(report)
        issues, stats = checks.citation_issues(citations, sources, set())
        self.assertEqual(stats.verified, 1)
        self.assertNotIn("unverified_url", {issue.type for issue in issues})

    def test_sources_listed_per_task_are_not_duplicates(self):
        report = (
            "# 报告\n\n## 一、结论\n\n见 https://llm-stats.com/benchmarks/mmmu-pro 。\n\n"
            "## 参考来源\n\n- A — https://llm-stats.com/benchmarks/mmmu-pro\n"
            "- B — https://llm-stats.com/benchmarks/mmmu-pro\n"
        )
        sources, citations, sections = build(report)
        issues, _stats = checks.citation_issues(citations, sources, set(), sections)
        self.assertNotIn("duplicate_citation", {issue.type for issue in issues})

    def test_duplicate_citation(self):
        report = (
            "# 报告\n\n## 一、结论\n\n"
            "见 https://llm-stats.com/benchmarks/mmmu-pro 。\n\n"
            "再看 https://llm-stats.com/benchmarks/mmmu-pro 。\n"
        )
        sources, citations, _ = build(report)
        issues, _stats = checks.citation_issues(citations, sources, set())
        duplicates = [issue for issue in issues if issue.type == "duplicate_citation"]
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].count, 2)

    def test_local_reference_missing(self):
        report = "# 报告\n\n## 一、结论\n\n见 local://documents/gone 。\n"
        sources, citations, _ = build(report)
        issues, stats = checks.citation_issues(citations, sources, set())
        self.assertEqual(stats.local_refs, 1)
        self.assertIn("local_ref_missing", {issue.type for issue in issues})

    def test_local_reference_present(self):
        report = "# 报告\n\n## 一、结论\n\n见 local://documents/kept 。\n"
        sources, citations, _ = build(report)
        issues, _stats = checks.citation_issues(citations, sources, {"kept"})
        self.assertNotIn("local_ref_missing", {issue.type for issue in issues})

    def test_uncited_source(self):
        report = "# 报告\n\n## 一、结论\n\n只引用 [MMMU](https://llm-stats.com/benchmarks/mmmu-pro)。\n"
        sources, citations, _ = build(report)
        issues, stats = checks.citation_issues(citations, sources, set())
        self.assertEqual(stats.uncited, 2)
        self.assertIn("uncited_source", {issue.type for issue in issues})


class StructureCheckTests(unittest.TestCase):
    def test_missing_conclusion_and_limitation(self):
        report = "# 报告\n\n## 一、背景\n\n" + ("背景介绍内容。" * 30) + "\n"
        _sources, citations, sections = build(report)
        issues, _empty = checks.structure_issues(report, sections, citations)
        types = {issue.type for issue in issues}
        self.assertIn("missing_conclusion", types)
        self.assertIn("missing_limitation", types)

    def test_complete_report_has_no_structure_errors(self):
        report = (
            "# 报告\n\n## 一、背景\n\n" + ("背景介绍内容。" * 30) + "\n\n"
            "## 二、结论\n\n" + ("结论内容。" * 30) + "\n\n"
            "## 三、局限与风险\n\n" + ("局限说明。" * 20) + "\n"
        )
        _sources, citations, sections = build(report)
        issues, _empty = checks.structure_issues(report, sections, citations)
        types = {issue.type for issue in issues}
        self.assertNotIn("missing_conclusion", types)
        self.assertNotIn("missing_limitation", types)

    def test_empty_report(self):
        issues, _empty = checks.structure_issues("   ", [], [])
        self.assertEqual([issue.type for issue in issues], ["empty_report"])

    def test_h1_title_section_is_not_flagged_as_empty(self):
        report = "# 报告标题\n\n## 一、结论\n\n" + ("结论内容。" * 30) + "\n"
        _sources, citations, sections = build(report)
        issues, _empty = checks.structure_issues(report, sections, citations)
        self.assertNotIn("empty_section", {issue.type for issue in issues})

    def test_parent_heading_with_subsections_is_not_empty(self):
        report = "# 报告\n\n## 三、证据\n\n### 3.1 细节\n\n" + ("证据内容。" * 30) + "\n"
        _sources, citations, sections = build(report)
        issues, _empty = checks.structure_issues(report, sections, citations)
        self.assertNotIn("empty_section", {issue.type for issue in issues})


class CoverageCheckTests(unittest.TestCase):
    def test_long_section_without_source(self):
        long_claim = "实验数据显示该方案提升明显，但这部分没有任何来源支撑，用来验证质检。" * 14
        report = (
            "# 报告\n\n## 一、背景\n\n短引用段，见 https://llm-stats.com/benchmarks/mmmu-pro 。\n\n"
            f"## 二、分析\n\n{long_claim}\n"
        )
        _sources, citations, sections = build(report)
        issues, without = checks.coverage_issues(sections, citations)
        self.assertGreaterEqual(without, 1)
        self.assertIn("no_source_section", {issue.type for issue in issues})

    def test_report_with_only_reference_list_gets_one_finding(self):
        report = (
            "# 报告\n\n## 一、背景\n\n" + ("背景介绍内容，没有任何行内引用。" * 20) + "\n\n"
            "## 参考来源\n\n- 来源 A — https://example.com/a\n- 来源 B — https://example.com/b\n"
        )
        _sources, citations, sections = build(report)
        issues, without = checks.coverage_issues(sections, citations)
        self.assertEqual([issue.type for issue in issues], ["no_inline_citations"])
        self.assertEqual(without, 0)

    def test_short_claim_section_is_not_flagged(self):
        report = (
            "# 报告\n\n## 一、背景\n\n见 https://example.com/a 。\n\n"
            "## 二、分析\n\n实验数据显示提升明显。\n"
        )
        _sources, citations, sections = build(report)
        issues, without = checks.coverage_issues(sections, citations)
        self.assertEqual(without, 0)


class SourceQualityTests(unittest.TestCase):
    def test_few_sources(self):
        sources = parse.merge_sources(parse.parse_sources("* 只有一条 : https://example.com/a"))
        issues = checks.source_quality_issues(sources, [])
        self.assertIn("few_sources", {issue.type for issue in issues})

    def test_domain_concentration(self):
        text = "".join(
            f"* 来源{i} : https://same.example.com/p{i}\n" for i in range(5)
        )
        sources = parse.merge_sources(parse.parse_sources(text))
        issues = checks.source_quality_issues(sources, [])
        self.assertIn("domain_concentration", {issue.type for issue in issues})

    def test_task_without_sources(self):
        sources = parse.merge_sources(parse.parse_sources(SOURCES_TEXT))
        tasks = [{"id": 3, "title": "未检索的任务", "status": "completed", "sources_summary": ""}]
        issues = checks.source_quality_issues(sources, tasks)
        self.assertIn("task_without_sources", {issue.type for issue in issues})

    def test_local_only_sources(self):
        sources = parse.merge_sources(
            parse.parse_sources("* [本地文献] 论文.docx : local://documents/d1")
        )
        issues = checks.source_quality_issues(sources, [])
        self.assertIn("local_only_sources", {issue.type for issue in issues})


class DeliveryCheckTests(unittest.TestCase):
    def test_missing_reference_section(self):
        report = "# 报告\n\n## 一、结论\n\n见 https://example.com/a 。\n"
        _sources, citations, sections = build(report)
        issues = checks.delivery_issues(report, sections, citations)
        self.assertIn("missing_reference_section", {issue.type for issue in issues})

    def test_mixed_citation_style(self):
        report = (
            "# 报告\n\n## 一、结论\n\n"
            "见 [链接](https://example.com/a) 与 https://example.com/b 。\n"
        )
        _sources, citations, sections = build(report)
        issues = checks.delivery_issues(report, sections, citations)
        self.assertIn("mixed_citation_style", {issue.type for issue in issues})

    def test_inline_links_plus_reference_list_is_not_mixed_style(self):
        report = (
            "# 报告\n\n## 一、结论\n\n见 [链接](https://example.com/a) 。\n\n"
            "## 参考来源\n\n- 来源一 — https://example.com/a\n"
        )
        _sources, citations, sections = build(report)
        issues = checks.delivery_issues(report, sections, citations)
        self.assertNotIn("mixed_citation_style", {issue.type for issue in issues})


class EngineTests(unittest.TestCase):
    def test_score_bounds_and_grade(self):
        bad = engine.audit("", [], [], set())
        self.assertEqual(bad["score"], 0)
        self.assertEqual(bad["grade"], "D")
        self.assertFalse(bad["report_available"])

    def test_good_report_scores_high(self):
        report = (
            "# 多模态研究报告\n\n"
            "## 一、背景\n\n" + ("背景介绍，见 [MMMU](https://llm-stats.com/benchmarks/mmmu-pro)。" * 8) + "\n\n"
            "## 二、结论\n\n" + ("结论如下，见 [STORM](https://research.nvidia.com/labs/lpr/storm)。" * 8) + "\n\n"
            "## 三、局限与风险\n\n" + ("局限说明内容。" * 20) + "\n"
        )
        sources = parse.merge_sources(parse.parse_sources(SOURCES_TEXT))
        result = engine.audit(report, sources, [], set())
        self.assertGreaterEqual(result["score"], 75)
        self.assertIn(result["grade"], {"A", "B"})
        self.assertEqual(result["metrics"]["unverified"], 0)

    def test_metrics_shape(self):
        result = engine.audit(
            "# 报告\n\n## 一、结论\n\n见 https://llm-stats.com/benchmarks/mmmu-pro 。\n",
            parse.merge_sources(parse.parse_sources(SOURCES_TEXT)),
            [],
            set(),
        )
        for key in (
            "cited_links", "cited_unique", "retrieved_unique", "verified",
            "unverified", "uncited", "coverage", "source_usage",
            "sections", "sections_without_source", "local_refs", "inline_citations",
            "references",
        ):
            self.assertIn(key, result["metrics"])
        self.assertEqual(result["metrics"]["verified"], 1)
        self.assertEqual(result["metrics"]["retrieved_unique"], 3)
        self.assertEqual(result["metrics"]["uncited"], 2)
        self.assertAlmostEqual(result["metrics"]["coverage"], 1.0)

    def test_audit_is_deterministic(self):
        report = "# 报告\n\n## 一、结论\n\n见 https://example.com/x 。\n"
        sources = parse.merge_sources(parse.parse_sources(SOURCES_TEXT))
        first = engine.audit(report, sources, [], set())
        second = engine.audit(report, sources, [], set())
        self.assertEqual(first, second)


class RenderingTests(unittest.TestCase):
    def test_quality_report_markdown(self):
        from quality import render

        result = engine.audit(
            "# 报告\n\n## 一、结论\n\n见 https://fake.example.com/x 。\n",
            [],
            [],
            set(),
        )
        markdown = render.render_quality_report(result, topic="测试主题", generated_at="2026-01-01")
        self.assertIn("# 报告质检单", markdown)
        self.assertIn("综合评分", markdown)
        self.assertIn("疑似编造", markdown)
        self.assertIn("测试主题", markdown)

    def test_reference_list_numbering(self):
        from quality import render

        rows = [
            {"index": 1, "url": "https://a.example.com/1", "title": "来源一", "kind": "web", "cited": True},
            {"index": 2, "url": "https://b.example.com/2", "title": "", "kind": "web", "cited": False},
        ]
        markdown = render.render_references(rows, style="plain")
        self.assertIn("[1] 来源一.", markdown)
        self.assertIn("[2] b.example.com.", markdown)
        self.assertIn("https://a.example.com/1", markdown)


if __name__ == "__main__":
    unittest.main()
