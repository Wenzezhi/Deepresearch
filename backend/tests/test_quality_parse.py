"""Reports are the only input of the quality gate; parsing must be exact."""
from __future__ import annotations

import unittest

from quality import checks, engine, parse, urls

REPORT = """# 研究报告

## 一、背景

多模态模型发展迅速，来源见 [MMMU-Pro 榜单](https://llm-stats.com/benchmarks/mmmu-pro)。

## 二、方法对比

- LoRA 与 Adapter 对比 — https://arxiv.org/abs/2106.09685
- 本地文献 D-1 — local://documents/doc1

## 参考来源

* MMMU-Pro Leaderboard : https://llm-stats.com/benchmarks/mmmu-pro
* STORM : https://research.nvidia.com/labs/lpr/storm
"""

FENCED = """# 报告

## 一、代码

```python
url = "https://inside-fence.example.com/secret"
```

正文引用 [真实来源](https://real.example.com/page)。
"""


class SectionTests(unittest.TestCase):
    def test_sections_and_reference_flag(self):
        sections = parse.split_sections(REPORT)
        headings = [section.heading for section in sections]
        self.assertEqual(headings, ["研究报告", "一、背景", "二、方法对比", "参考来源"])
        self.assertEqual(sections[-1].level, 2)
        self.assertTrue(sections[-1].is_reference)
        self.assertFalse(sections[1].is_reference)

    def test_heading_inside_code_fence_is_ignored(self):
        report = "# 标题\n\n```\n## 假的标题\n```\n\n## 真标题\n\n内容"
        sections = parse.split_sections(report)
        self.assertEqual([section.heading for section in sections], ["标题", "真标题"])

    def test_section_body_length(self):
        sections = parse.split_sections(REPORT)
        background = next(section for section in sections if section.heading == "一、背景")
        self.assertGreater(background.body_length, 10)


class SourceParsingTests(unittest.TestCase):
    def test_colon_dash_and_local_forms(self):
        text = (
            "* MMMU-Pro Leaderboard : https://llm-stats.com/benchmarks/mmmu-pro\n"
            "- STORM — https://research.nvidia.com/labs/lpr/storm\n"
            "* [本地文献 D-34] 低资源多模态适配.docx : local://documents/34dab0e2\n"
            "这一行不是来源\n"
        )
        sources = parse.parse_sources(text, task_id=2)
        self.assertEqual(len(sources), 3)
        self.assertEqual(sources[0].title, "MMMU-Pro Leaderboard")
        self.assertEqual(sources[0].kind, "web")
        self.assertEqual(sources[0].task_ids, [2])
        self.assertEqual(sources[1].title, "STORM")
        self.assertEqual(sources[2].title, "低资源多模态适配.docx")
        self.assertEqual(sources[2].kind, "local")
        self.assertEqual(urls.local_document_id(sources[2].url), "34dab0e2")

    def test_merge_sources_dedupes_and_merges_tasks(self):
        first = parse.parse_sources("* 标题 : https://example.com/a?utm_source=x", task_id=1)
        second = parse.parse_sources("* 标题 : https://example.com/a", task_id=2)
        merged = parse.merge_sources([*first, *second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(sorted(merged[0].task_ids), [1, 2])


class CitationParsingTests(unittest.TestCase):
    def test_all_forms_are_extracted_once(self):
        citations = parse.extract_citations(REPORT)
        self.assertEqual(len(citations), 5)
        forms = [citation.form for citation in citations]
        self.assertEqual(forms.count("markdown"), 1)
        self.assertEqual(forms.count("bullet"), 3)  # 正文 1 条 + 参考来源 2 条
        self.assertEqual(forms.count("local"), 1)

    def test_markdown_link_is_not_counted_twice_as_bare_url(self):
        citations = parse.extract_citations(
            "见 [来源一](https://example.com/a) 与 https://example.com/b"
        )
        self.assertEqual(len(citations), 2)

    def test_citation_keeps_section(self):
        citations = parse.extract_citations(REPORT)
        by_section = {citation.section for citation in citations}
        self.assertIn("一、背景", by_section)
        self.assertIn("二、方法对比", by_section)
        self.assertIn("参考来源", by_section)

    def test_url_inside_code_fence_is_ignored(self):
        citations = parse.extract_citations(FENCED)
        urls_found = {citation.url for citation in citations}
        self.assertIn("https://real.example.com/page", urls_found)
        self.assertNotIn("https://inside-fence.example.com/secret", urls_found)

    def test_quote_is_the_sentence_around_the_citation(self):
        report = (
            "# 报告\n\n## 一、背景\n\n"
            "第一句无关内容。第二句才提到 [关键来源](https://example.com/a)。第三句结尾。\n"
        )
        citations = parse.extract_citations(report)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].form, "markdown")
        self.assertIn("第二句", citations[0].quote)
        self.assertIn("关键来源", citations[0].quote)
        self.assertNotIn("第一句", citations[0].quote)

    def test_bare_url_quote_is_the_sentence(self):
        report = "## 一、结论\n\n实验数据显示提升明显 https://example.com/b 。随后是无关内容。\n"
        citations = parse.extract_citations(report)
        bare = [citation for citation in citations if citation.form == "bare"]
        self.assertTrue(bare)
        self.assertIn("实验数据", bare[0].quote)


class NumberedCitationTests(unittest.TestCase):
    REPORT = """# 报告

## 一、结论

原生统一架构在同等算力下不劣于 late-fusion[1]。长视频先注入时序再压缩[2]。

## 参考文献

[1] Native Multimodal Models. arxiv.org. https://arxiv.org/html/2605.25343v1
[2] STORM. research.nvidia.com. https://research.nvidia.com/labs/lpr/storm
"""

    def test_numbered_reference_list_is_parsed(self):
        sources = parse.parse_sources(self.REPORT)
        numbers = [(source.number, source.title) for source in sources]
        self.assertIn((1, "Native Multimodal Models. arxiv.org"), numbers)
        self.assertEqual(sources[0].kind, "web")

    def test_numeric_citations_are_resolved_to_urls(self):
        sources = parse.merge_sources(parse.parse_sources(self.REPORT))
        citations = parse.extract_citations(self.REPORT)
        numeric = [citation for citation in citations if citation.form == "numeric"]
        self.assertEqual([citation.number for citation in numeric], [1, 2])
        resolved, unresolved = parse.resolve_numbered_citations(citations, sources)
        self.assertEqual(unresolved, set())
        by_number = {citation.number: citation for citation in resolved if citation.form == "numeric"}
        self.assertEqual(by_number[1].url, "https://arxiv.org/html/2605.25343v1")
        self.assertEqual(by_number[2].normalized, "https://research.nvidia.com/labs/lpr/storm")

    def test_numbers_resolve_from_report_reference_list(self):
        # 检索事件的来源没有编号；编号来自报告自己的参考文献表
        citations = parse.extract_citations(self.REPORT)
        resolved, unresolved = parse.resolve_numbered_citations(citations, [])
        self.assertEqual(unresolved, set())
        numeric = {c.number: c for c in resolved if c.form == "numeric"}
        self.assertEqual(numeric[1].url, "https://arxiv.org/html/2605.25343v1")

    def test_repeated_numeric_citations_are_not_duplicates(self):
        report = (
            "## 一、结论\n\n结论 A[1]。结论 B[1]。\n\n"
            "## 参考文献\n\n[1] T. d. https://example.com/a\n"
        )
        sources = parse.merge_sources(parse.parse_sources(report))
        citations, _unresolved = parse.resolve_numbered_citations(
            parse.extract_citations(report), sources
        )
        issues, _stats = checks.citation_issues(citations, sources, set())
        self.assertNotIn("duplicate_citation", {issue.type for issue in issues})

    def test_uncited_reference_from_report_list(self):
        report = (
            "## 一、结论\n\n结论[1]。\n\n"
            "## 参考文献\n\n[1] A. d. https://example.com/a\n[2] B. d. https://example.com/b\n"
        )
        sources = parse.merge_sources(parse.parse_sources(report))
        citations, unresolved = parse.resolve_numbered_citations(
            parse.extract_citations(report), sources
        )
        issues = checks.numbered_citation_issues(citations, sources, unresolved)
        uncited = [issue for issue in issues if issue.type == "uncited_reference"]
        self.assertEqual([issue.number for issue in uncited], [2])

    def test_audit_lists_all_references_with_status(self):
        report = self.REPORT.replace("再压缩[2]。", "再压缩[9]。")
        sources = parse.merge_sources(parse.parse_sources(report))
        result = engine.audit(report, sources, [], set())
        refs = {row["number"]: row for row in result["references"]}
        self.assertEqual(sorted(refs), [1, 2, 9])
        self.assertTrue(refs[1]["verified"])
        self.assertTrue(refs[1]["cited_in_body"])
        self.assertFalse(refs[2]["cited_in_body"])
        self.assertIn("unresolved_citation_number", refs[9]["issue_types"])
        self.assertEqual(result["metrics"]["references"], 2)

    def test_quality_report_contains_reference_table(self):
        from quality import render

        sources = parse.merge_sources(parse.parse_sources(self.REPORT))
        result = engine.audit(self.REPORT, sources, [], set())
        markdown = render.render_quality_report(result, topic="测试")
        self.assertIn("## 三、参考文献核验", markdown)
        self.assertIn("| [1] |", markdown)

    def test_unresolved_number_is_reported(self):
        report = self.REPORT.replace("再压缩[2]。", "再压缩[9]。")
        sources = parse.merge_sources(parse.parse_sources(report))
        citations, unresolved = parse.resolve_numbered_citations(
            parse.extract_citations(report), sources
        )
        self.assertEqual(unresolved, {9})
        issues = checks.numbered_citation_issues(citations, sources, unresolved)
        types = {issue.type for issue in issues}
        self.assertIn("unresolved_citation_number", types)
        self.assertIn("uncited_reference", types)


class UrlNormalisationTests(unittest.TestCase):
    def test_tracking_and_fragment_removed(self):
        self.assertEqual(
            urls.normalize("https://www.Example.com/path/?utm_source=x&utm_medium=y#frag"),
            "https://example.com/path",
        )

    def test_trailing_slash_and_scheme_are_normalised(self):
        self.assertEqual(urls.normalize("http://example.com/a/"), "https://example.com/a")

    def test_meaningful_query_is_sorted_but_kept(self):
        self.assertEqual(
            urls.normalize("https://example.com/search?b=2&a=1"),
            "https://example.com/search?a=1&b=2",
        )

    def test_local_urls(self):
        self.assertTrue(urls.is_local("local://documents/abc"))
        self.assertEqual(urls.normalize("local://documents/abc"), "local:abc")
        self.assertEqual(urls.domain("local://documents/abc"), "本地资料库")


if __name__ == "__main__":
    unittest.main()
