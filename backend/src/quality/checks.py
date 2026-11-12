"""Rule-based checks for a generated research report.

Every check is a pure function over parsed report data; nothing here touches
the database, the network or the research pipeline.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from . import urls
from .parse import Citation, Section, Source

ERROR = "error"
WARN = "warn"
INFO = "info"

_SECTION_MIN_CHARS = 400
_EMPTY_SECTION_CHARS = 50
_SHORT_REPORT_CHARS = 800
_CLAIM_PATTERN = re.compile(
    r"\d|表明|显示|证明|提升|下降|显著|因此|结论|数据|实验|对比|增幅|占比|优于|弱于"
)

_CONCLUSION = re.compile(r"结论|总结|结语|小结|结论与展望")
_LIMITATION = re.compile(r"局限|不足|风险|挑战|限制|边界")
_REFERENCE_TEXT = re.compile(r"参考(?:来源|文献|资料)|References?", re.I)


@dataclass
class Issue:
    type: str
    severity: str
    message: str
    url: str | None = None
    title: str | None = None
    section: str | None = None
    task_id: int | None = None
    line: int | None = None
    snippet: str | None = None
    quote: str | None = None
    number: int | None = None
    count: int | None = None

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


@dataclass
class CitationStats:
    cited_links: int = 0
    cited_unique: int = 0
    retrieved_unique: int = 0
    verified: int = 0
    unverified: int = 0
    uncited: int = 0
    local_refs: int = 0
    sections: int = 0
    sections_without_source: int = 0
    cited_http: set[str] = field(default_factory=set)
    retrieved_http: set[str] = field(default_factory=set)
    local_ids: set[str] = field(default_factory=set)

    @property
    def coverage(self) -> float:
        if not self.cited_unique:
            return 0.0
        return round(self.verified / self.cited_unique, 3)

    @property
    def source_usage(self) -> float:
        if not self.retrieved_unique:
            return 0.0
        return round(self.verified / self.retrieved_unique, 3)


def _snippet(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def citation_issues(
    citations: list[Citation],
    sources: list[Source],
    known_document_ids: set[str],
    sections: list[Section] | None = None,
) -> tuple[list[Issue], CitationStats]:
    """Citations vs. what the run actually retrieved."""
    reference_ranges = [
        (section.line_start, section.line_end)
        for section in (sections or [])
        if section.is_reference
    ]

    def in_reference(line: int) -> bool:
        return any(start <= line < end for start, end in reference_ranges)

    stats = CitationStats(cited_links=len(citations))
    issues: list[Issue] = []

    retrieved: dict[str, Source] = {
        source.normalized: source for source in sources if source.kind == "web"
    }
    stats.retrieved_http = set(retrieved)
    stats.retrieved_unique = len(retrieved)

    counts: dict[str, int] = {}
    body_counts: dict[str, int] = {}
    first_seen: dict[str, Citation] = {}
    local_counts: dict[str, int] = {}
    for citation in citations:
        if citation.is_local:
            document_id = urls.local_document_id(citation.url)
            stats.local_refs += 1
            local_counts[document_id] = local_counts.get(document_id, 0) + 1
            continue
        # 编号引用 [1] 被多次使用是规范写法，不算重复引用
        if citation.form == "numeric":
            continue
        key = citation.normalized
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        # 文末来源列表按任务各列一次是正常写法，只统计正文内的重复
        if not in_reference(citation.line):
            body_counts[key] = body_counts.get(key, 0) + 1
        first_seen.setdefault(key, citation)

    stats.cited_http = set(counts)
    stats.cited_unique = len(stats.cited_http)
    stats.verified = len(stats.cited_http & stats.retrieved_http)
    stats.unverified = len(stats.cited_http - stats.retrieved_http)
    stats.uncited = len(stats.retrieved_http - stats.cited_http)

    for key in sorted(stats.cited_http - stats.retrieved_http):
        citation = first_seen[key]
        section = citation.section or None
        issues.append(Issue(
            type="unverified_url",
            severity=ERROR,
            message="该链接不在本次研究的检索结果中，可能是模型编造或来自旧知识，请人工核对",
            url=citation.url,
            title=citation.text or None,
            section=section,
            line=citation.line,
            snippet=_snippet(citation.snippet or citation.text or citation.url),
            quote=citation.quote or None,
        ))

    for key in sorted(stats.retrieved_http - stats.cited_http):
        source = retrieved[key]
        issues.append(Issue(
            type="uncited_source",
            severity=INFO,
            message="检索到了该来源，但报告没有引用它",
            url=source.url,
            title=source.title,
            task_id=source.task_ids[0] if source.task_ids else None,
        ))

    for key, count in sorted(body_counts.items()):
        if count < 2:
            continue
        citation = first_seen[key]
        issues.append(Issue(
            type="duplicate_citation",
            severity=WARN,
            message=f"同一链接在报告中出现了 {count} 次",
            url=citation.url,
            title=citation.text or None,
            section=citation.section or None,
            line=citation.line,
            snippet=_snippet(citation.snippet or ""),
            quote=citation.quote or None,
            count=count,
        ))

    for document_id, count in sorted(local_counts.items()):
        if document_id in known_document_ids:
            continue
        issues.append(Issue(
            type="local_ref_missing",
            severity=ERROR,
            message=f"报告引用的本地文献已不存在（共引用 {count} 次），请重新上传后再导出",
            url=urls.make_local_url(document_id),
            count=count,
        ))

    return issues, stats


def numbered_citation_issues(
    citations: list[Citation],
    sources: list[Source],
    unresolved: set[int],
) -> list[Issue]:
    """``[n]`` body citations vs. the numbered reference list."""
    issues: list[Issue] = []
    for number in sorted(unresolved):
        first = next(
            (citation for citation in citations
             if citation.form == "numeric" and citation.number == number),
            None,
        )
        issues.append(Issue(
            type="unresolved_citation_number",
            severity=ERROR,
            message=f"正文引用了编号 [{number}]，但参考文献表里找不到对应条目",
            section=first.section if first else None,
            line=first.line if first else None,
            quote=first.quote if first else None,
            number=number,
        ))

    numeric = [citation for citation in citations if citation.form == "numeric"]
    if numeric:
        cited_numbers = {citation.number for citation in numeric}
        reference_entries = [
            citation for citation in citations
            if citation.form == "reference" and citation.number is not None
        ]
        if reference_entries:
            uncited_refs = [
                (entry.number, entry.text, entry.url) for entry in reference_entries
                if entry.number not in cited_numbers
            ]
        else:
            uncited_refs = [
                (source.number, source.title, source.url)
                for source in sources
                if source.number is not None and source.number not in cited_numbers
            ]
        for number, title, url in uncited_refs[:5]:
            issues.append(Issue(
                type="uncited_reference",
                severity=INFO,
                message=f"参考文献 [{number}] 在正文中没有被引用",
                title=title or None,
                url=url or None,
                number=number,
            ))
    return issues


def structure_issues(report: str, sections: list[Section], citations: list[Citation]) -> tuple[list[Issue], int]:
    """Structural completeness of the report itself."""
    issues: list[Issue] = []
    stripped = report.strip()
    if not stripped:
        issues.append(Issue(
            type="empty_report", severity=ERROR,
            message="研究还没有生成最终报告，无法质检",
        ))
        return issues, 0

    headings = [section for section in sections if section.heading]
    if not any(_CONCLUSION.search(section.heading) for section in headings):
        issues.append(Issue(
            type="missing_conclusion", severity=WARN,
            message="报告没有独立结论段（含「结论/总结/小结」等标题），读者难以快速抓住要点",
        ))

    if not any(_LIMITATION.search(section.heading) for section in headings):
        issues.append(Issue(
            type="missing_limitation", severity=INFO,
            message="报告没有局限/风险说明段落，建议补充研究边界",
        ))

    heading_sections = [section for section in sections if section.heading]
    empty_count = 0
    for index, section in enumerate(heading_sections):
        if section.is_reference or section.level <= 1:
            continue
        # 有子标题的父章节（只有标题、内容都在子章节里）不算空章节
        following = heading_sections[index + 1] if index + 1 < len(heading_sections) else None
        if following is not None and following.level > section.level:
            continue
        if section.body_length < _EMPTY_SECTION_CHARS:
            empty_count += 1
            if empty_count <= 3:
                issues.append(Issue(
                    type="empty_section", severity=WARN,
                    message=f"章节「{section.heading}」几乎没有正文内容（{section.body_length} 字）",
                    section=section.heading,
                ))

    previous_level = 0
    jump_issues = 0
    for section in headings:
        if section.level and previous_level and section.level > previous_level + 1 and jump_issues < 2:
            issues.append(Issue(
                type="heading_level_jump", severity=INFO,
                message=f"标题层级从 H{previous_level} 跳到 H{section.level}，结构可能不完整",
                section=section.heading,
            ))
            jump_issues += 1
        if section.level:
            previous_level = section.level

    if len(stripped) < _SHORT_REPORT_CHARS:
        issues.append(Issue(
            type="report_too_short", severity=WARN,
            message=f"报告正文只有 {len(stripped)} 字，可能不足以支撑研究结论",
        ))

    return issues, empty_count


def _citation_in_reference(citation: Citation, sections: list[Section]) -> bool:
    for section in sections:
        if section.is_reference and section.line_start <= citation.line < section.line_end:
            return True
    return False


def inline_citations(sections: list[Section], citations: list[Citation]) -> list[Citation]:
    """Citations that appear in the report body rather than a reference list."""
    return [citation for citation in citations if not _citation_in_reference(citation, sections)]


def _representative_sentence(section: Section) -> str:
    """Pick a claim-bearing sentence so the UI can jump into the section body."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", section.body) if part.strip()]
    if not paragraphs:
        paragraphs = [section.body.strip()] if section.body.strip() else []
    if not paragraphs:
        return ""
    candidates = [part for part in paragraphs if _CLAIM_PATTERN.search(part)] or paragraphs
    longest = max(candidates, key=len)
    first = re.split(r"(?<=[。！？；!?;])", longest)[0].strip()
    return _snippet(first, 160)


def coverage_issues(
    sections: list[Section], citations: list[Citation]
) -> tuple[list[Issue], int]:
    """Long claim-bearing sections that carry no inline citation.

    A report that only dumps URLs into a trailing reference list gets a single
    explicit finding instead of one noisy warning per section.
    """
    issues: list[Issue] = []
    inline = inline_citations(sections, citations)

    if citations and not inline:
        return [
            Issue(
                type="no_inline_citations",
                severity=WARN,
                message=(
                    "全文没有任何行内引用：来源只堆在文末参考文献里，读者无法判断"
                    "哪条结论来自哪条来源"
                ),
            )
        ], 0

    without = 0
    for section in sections:
        if section.is_reference or section.level == 0:
            continue
        if section.body_length < _SECTION_MIN_CHARS:
            continue
        if any(section.line_start <= citation.line < section.line_end for citation in inline):
            continue
        if not _CLAIM_PATTERN.search(section.body):
            continue
        without += 1
        if without <= 4:
            issues.append(Issue(
                type="no_source_section",
                severity=INFO,
                message=(
                    f"该章节 {section.body_length} 字、包含具体结论，"
                    "但没有任何行内引用，结论无法核验"
                ),
                section=section.heading,
                snippet=_representative_sentence(section) or None,
            ))
    return issues, without


def source_quality_issues(
    sources: list[Source], tasks: list[dict[str, Any]]
) -> list[Issue]:
    """The retrieved source set itself: size, diversity, per-task coverage."""
    issues: list[Issue] = []
    web = [source for source in sources if source.kind == "web"]
    if not web:
        if sources:
            issues.append(Issue(
                type="local_only_sources", severity=INFO,
                message="本次研究只用到本地文献，没有网络来源，结论的时效性需要自行确认",
            ))
        return issues

    if len(web) < 3:
        issues.append(Issue(
            type="few_sources", severity=WARN,
            message=f"本次研究只检索到 {len(web)} 条网络来源，覆盖面偏窄",
        ))

    domain_counts: dict[str, int] = {}
    for source in web:
        domain_counts[source.domain] = domain_counts.get(source.domain, 0) + 1
    if domain_counts:
        top_domain, top_count = max(domain_counts.items(), key=lambda item: item[1])
        share = top_count / len(web)
        if share >= 0.6 and top_count >= 3:
            issues.append(Issue(
                type="domain_concentration", severity=WARN,
                message=f"{int(share * 100)}% 的来源来自 {top_domain}，来源多样性不足",
                title=top_domain,
            ))

    for task in tasks:
        status = str(task.get("status") or "")
        if status not in {"completed", "in_progress", "skipped"}:
            continue
        if task.get("sources_summary"):
            continue
        if status == "skipped":
            continue
        issues.append(Issue(
            type="task_without_sources", severity=WARN,
            message=f"任务「{task.get('title') or '未命名'}」没有任何来源记录",
            task_id=task.get("id"),
            section=str(task.get("title") or "") or None,
        ))
        if len(issues) > 8:
            break
    return issues


def delivery_issues(
    report: str, sections: list[Section], citations: list[Citation]
) -> list[Issue]:
    """Things to fix right before handing the report to someone else."""
    issues: list[Issue] = []
    reference_sections = [section for section in sections if section.is_reference]
    if not reference_sections:
        issues.append(Issue(
            type="missing_reference_section", severity=INFO,
            message="报告没有参考文献/来源段落，交付前建议补一份规范来源表",
        ))
    else:
        cited_in_refs = sum(
            1 for citation in citations
            for section in reference_sections
            if section.line_start <= citation.line < section.line_end
        )
        if not cited_in_refs:
            issues.append(Issue(
                type="empty_reference_section", severity=WARN,
                message="报告有「参考来源」标题，但下面没有任何链接",
            ))

    reference_ranges = [
        (section.line_start, section.line_end)
        for section in sections
        if section.is_reference
    ]

    def in_reference(line: int) -> bool:
        return any(start <= line < end for start, end in reference_ranges)

    # 只比较正文内的链接写法；正文用链接 + 文末用列表是正常写法
    forms = {
        citation.form
        for citation in citations
        if citation.form in {"markdown", "bullet", "bare"} and not in_reference(citation.line)
    }
    if len(forms) >= 2:
        issues.append(Issue(
            type="mixed_citation_style", severity=INFO,
            message="报告里的链接写法不统一（混用了 markdown 链接、短横线列表和裸链接），建议统一",
        ))

    if citations and any(not citation.text for citation in citations if citation.form == "markdown"):
        issues.append(Issue(
            type="unlabelled_link", severity=INFO,
            message="部分链接没有可读的链接文字，读者无法判断来源内容",
        ))
    return issues


def pick_issue_counts(issues: list[Issue]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.type] = counts.get(issue.type, 0) + 1
    return counts
