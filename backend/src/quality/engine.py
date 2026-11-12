"""Assemble the report audit: metrics, issues, score and source list."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from . import checks, parse, urls
from .checks import Issue

# Penalty per issue type, with an optional cap per type.
_PENALTY: dict[str, tuple[int, int]] = {
    "empty_report": (100, 100),
    "unverified_url": (12, 36),
    "local_ref_missing": (8, 16),
    "unresolved_citation_number": (10, 20),
    "uncited_reference": (1, 5),
    "report_too_short": (6, 6),
    "few_sources": (10, 10),
    "missing_conclusion": (8, 8),
    "domain_concentration": (5, 5),
    "empty_section": (4, 12),
    "task_without_sources": (4, 8),
    "missing_limitation": (4, 4),
    "missing_reference_section": (4, 4),
    "no_source_section": (3, 12),
    "empty_reference_section": (3, 3),
    "local_only_sources": (3, 3),
    "duplicate_citation": (2, 6),
    "no_inline_citations": (6, 6),
    "heading_level_jump": (2, 4),
    "mixed_citation_style": (2, 2),
    "unlabelled_link": (1, 2),
}

_GRADES = ((90, "A"), (75, "B"), (60, "C"))


def _grade(score: int) -> str:
    for threshold, grade in _GRADES:
        if score >= threshold:
            return grade
    return "D"


def _score(issues: list[Issue]) -> int:
    totals: dict[str, int] = {}
    for issue in issues:
        weight, _cap = _PENALTY.get(issue.type, (1, 1))
        totals[issue.type] = totals.get(issue.type, 0) + weight
    deductions = 0
    for issue_type, total in totals.items():
        _weight, cap = _PENALTY.get(issue_type, (1, 1))
        deductions += min(total, cap)
    return max(0, min(100, 100 - deductions))


def _public_sources(
    sources: list[parse.Source],
    citations: list[parse.Citation],
) -> list[dict[str, Any]]:
    """Ordered source list: cited sources first (in report order), then the rest."""
    retrieved = {source.normalized: source for source in sources if source.kind == "web"}
    order: list[str] = []
    seen: set[str] = set()
    cited_keys = {citation.normalized for citation in citations if not citation.is_local}
    for citation in citations:
        if citation.is_local:
            continue
        key = citation.normalized
        if key and key not in seen:
            seen.add(key)
            order.append(key)
    for key in sorted(retrieved):
        if key not in seen:
            seen.add(key)
            order.append(key)

    rows: list[dict[str, Any]] = []
    for index, key in enumerate(order, start=1):
        source = retrieved.get(key)
        if source is None:
            first = next(
                (citation for citation in citations if citation.normalized == key),
                None,
            )
            rows.append({
                "index": index,
                "url": first.url if first else key,
                "title": (first.text if first and first.text else urls.domain(first.url) if first else key),
                "domain": urls.domain(first.url) if first else "",
                "kind": "web",
                "task_ids": [],
                "cited": True,
                "verified": False,
                "number": first.number if first else None,
            })
            continue
        rows.append({
            "index": index,
            "url": source.url,
            "title": source.title,
            "domain": source.domain,
            "kind": source.kind,
            "task_ids": source.task_ids,
            "cited": key in cited_keys,
            "verified": True,
            "number": source.number,
        })
    return rows


def _public_citations(
    citations: list[parse.Citation], sections: list[parse.Section]
) -> list[dict[str, Any]]:
    """Every citation with its location, so the reader can jump to the text."""
    reference_ranges = [
        (section.line_start, section.line_end)
        for section in sections
        if section.is_reference
    ]
    rows: list[dict[str, Any]] = []
    for citation in citations:
        rows.append({
            "url": citation.url,
            "title": citation.text,
            "form": citation.form,
            "section": citation.section,
            "line": citation.line,
            "snippet": citation.snippet,
            "quote": citation.quote,
            "number": citation.number,
            "in_reference": any(
                start <= citation.line < end for start, end in reference_ranges
            ),
        })
    return rows


def _public_references(
    citations: list[parse.Citation],
    sources: list[parse.Source],
    unresolved: set[int],
) -> list[dict[str, Any]]:
    """Every reference-list entry with its verification status."""
    retrieved = {source.normalized for source in sources if source.kind == "web"}
    numeric_numbers = {
        citation.number for citation in citations if citation.form == "numeric"
    }
    rows: list[dict[str, Any]] = []
    for citation in citations:
        if citation.form != "reference" or citation.number is None:
            continue
        verified = citation.normalized in retrieved
        cited_in_body = citation.number in numeric_numbers
        issue_types: list[str] = []
        if not verified:
            issue_types.append("unverified_url")
        if not cited_in_body:
            issue_types.append("uncited_reference")
        rows.append({
            "number": citation.number,
            "title": citation.text,
            "url": citation.url,
            "domain": urls.domain(citation.url),
            "verified": verified,
            "cited_in_body": cited_in_body,
            "issue_types": issue_types,
        })
    for number in sorted(unresolved):
        rows.append({
            "number": number,
            "title": "（参考文献表缺少该条目）",
            "url": None,
            "domain": "",
            "verified": False,
            "cited_in_body": True,
            "issue_types": ["unresolved_citation_number"],
        })
    rows.sort(key=lambda row: row["number"])
    return rows


def audit(
    report: str,
    sources: list[parse.Source],
    tasks: list[dict[str, Any]] | None = None,
    known_document_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Run every check and return a JSON-serialisable audit result."""
    tasks = tasks or []
    known_document_ids = known_document_ids or set()
    report = report or ""

    sections = parse.split_sections(report)
    citations = parse.extract_citations(report)
    citations, unresolved_numbers = parse.resolve_numbered_citations(citations, sources)

    citation_issues, stats = checks.citation_issues(citations, sources, known_document_ids, sections)
    number_issue_list = checks.numbered_citation_issues(citations, sources, unresolved_numbers)
    structure_issue_list, _empty_sections = checks.structure_issues(report, sections, citations)
    coverage_issue_list, without_source = checks.coverage_issues(sections, citations)
    quality_issue_list = checks.source_quality_issues(sources, tasks)
    delivery_issue_list = checks.delivery_issues(report, sections, citations)

    issues = [
        *citation_issues,
        *number_issue_list,
        *structure_issue_list,
        *coverage_issue_list,
        *quality_issue_list,
        *delivery_issue_list,
    ]
    severity_order = {checks.ERROR: 0, checks.WARN: 1, checks.INFO: 2}
    issues.sort(key=lambda issue: (severity_order.get(issue.severity, 3), issue.type))

    stats.sections = len([section for section in sections if section.level > 0])
    stats.sections_without_source = without_source

    inline = checks.inline_citations(sections, citations)

    score = _score(issues)
    summary = {checks.ERROR: 0, checks.WARN: 0, checks.INFO: 0}
    for issue in issues:
        summary[issue.severity] = summary.get(issue.severity, 0) + 1

    metrics = asdict(stats)
    metrics.pop("cited_http", None)
    metrics.pop("retrieved_http", None)
    metrics.pop("local_ids", None)
    metrics["coverage"] = stats.coverage
    metrics["source_usage"] = stats.source_usage
    metrics["inline_citations"] = len(inline)
    metrics["numeric_citations"] = len(
        [citation for citation in citations if citation.form == "numeric"]
    )
    metrics["references"] = len(
        [citation for citation in citations if citation.form == "reference"]
    )

    return {
        "report_available": bool(report.strip()),
        "metrics": metrics,
        "score": score,
        "grade": _grade(score),
        "issues": [issue.public() for issue in issues],
        "issue_summary": summary,
        "sources": _public_sources(sources, citations),
        "citations": _public_citations(citations, sections),
        "references": _public_references(citations, sources, unresolved_numbers),
    }
