"""Render the quality report and the normalised reference list as Markdown."""
from __future__ import annotations

from typing import Any

from . import urls

SEVERITY_LABEL = {
    "error": "严重",
    "warn": "警告",
    "info": "提示",
}

ISSUE_LABEL = {
    "unverified_url": "疑似编造/未核验链接",
    "local_ref_missing": "本地文献已被删除",
    "duplicate_citation": "重复引用",
    "no_source_section": "章节无来源",
    "missing_conclusion": "缺少结论段",
    "missing_limitation": "缺少局限说明",
    "empty_section": "空章节",
    "heading_level_jump": "标题层级跳跃",
    "report_too_short": "报告过短",
    "few_sources": "来源过少",
    "domain_concentration": "来源过于集中",
    "task_without_sources": "任务没有来源",
    "local_only_sources": "只有本地来源",
    "missing_reference_section": "缺少参考文献段",
    "empty_reference_section": "参考文献段为空",
    "mixed_citation_style": "链接写法不统一",
    "unlabelled_link": "链接缺少可读文字",
    "no_inline_citations": "全文无行内引用",
    "empty_report": "报告为空",
}


def _issue_line(index: int, issue: dict[str, Any]) -> str:
    label = ISSUE_LABEL.get(issue.get("type", ""), issue.get("type", "问题"))
    location = issue.get("section") or ""
    if issue.get("task_id") is not None:
        location = f"任务 {issue['task_id']}" + (f" / {location}" if location else "")
    suffix = f"（{location}）" if location else ""
    url = issue.get("url")
    link = f" {url}" if url else ""
    return f"{index}. **{label}**{suffix}：{issue.get('message', '')}{link}"


def render_quality_report(result: dict[str, Any], topic: str = "", generated_at: str = "") -> str:
    """Render the one-page quality report users can attach to their document."""
    metrics = result.get("metrics", {})
    issues = result.get("issues", [])
    summary = result.get("issue_summary", {})

    lines: list[str] = ["# 报告质检单"]
    if topic:
        lines.append(f"- 研究主题：{topic}")
    if generated_at:
        lines.append(f"- 质检时间：{generated_at}")
    lines.append(f"- 综合评分：**{result.get('score', 0)} / 100**（等级 {result.get('grade', 'D')}）")
    lines.append("")

    lines.append("## 一、总体结论")
    grade = result.get("grade", "D")
    total_issues = sum(summary.values()) if summary else len(issues)
    if not result.get("report_available"):
        lines.append("> 尚未生成最终报告，暂无法质检。")
    elif grade == "A":
        lines.append(f"> 报告结构完整、引用可核验，共发现 {total_issues} 处可优化项，可直接交付。")
    elif grade == "B":
        lines.append(f"> 报告整体可用，共发现 {total_issues} 处问题，建议按下方清单修改后交付。")
    elif grade == "C":
        lines.append(f"> 报告存在较多可核验性问题（{total_issues} 处），交付前需要人工复核来源与结构。")
    else:
        lines.append(f"> 报告质量问题较多（{total_issues} 处），不建议直接交付。")
    lines.append("")

    lines.append("## 二、体检指标")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 报告引用数 | {metrics.get('cited_links', 0)} |")
    lines.append(f"| 其中行内引用 | {metrics.get('inline_citations', 0)} |")
    lines.append(f"| 去重后引用 | {metrics.get('cited_unique', 0)} |")
    lines.append(f"| 检索来源数 | {metrics.get('retrieved_unique', 0)} |")
    lines.append(f"| 可核验引用 | {metrics.get('verified', 0)} |")
    lines.append(f"| 疑似编造链接 | {metrics.get('unverified', 0)} |")
    lines.append(f"| 未被引用的来源 | {metrics.get('uncited', 0)} |")
    lines.append(f"| 引用可核验率 | {int(metrics.get('coverage', 0) * 100)}% |")
    lines.append(f"| 无来源章节 | {metrics.get('sections_without_source', 0)} |")
    lines.append("")

    lines.append("## 三、问题清单")
    lines.append("")
    if not issues:
        lines.append("未发现问题。")
    else:
        counter = 1
        for severity in ("error", "warn", "info"):
            group = [issue for issue in issues if issue.get("severity") == severity]
            if not group:
                continue
            lines.append(f"### {SEVERITY_LABEL[severity]}（{len(group)}）")
            for issue in group:
                lines.append(_issue_line(counter, issue))
                counter += 1
            lines.append("")

    lines.append("## 四、交付建议")
    lines.append("")
    suggestions: list[str] = []
    if metrics.get("unverified", 0):
        suggestions.append("逐条核对「疑似编造/未核验链接」，无法核实的结论请降级表述或删除。")
    if any(issue.get("type") == "no_inline_citations" for issue in issues):
        suggestions.append("把文末来源对应到具体结论：在关键段落补行内引用（[n] 或链接）。")
    if metrics.get("sections_without_source", 0):
        suggestions.append("为无来源的长章节补充引用，或明确标注为「作者分析」。")
    if metrics.get("uncited", 0):
        suggestions.append("从「未被引用的来源」中挑选高价值文献补进参考文献表。")
    if any(issue.get("type") == "missing_reference_section" for issue in issues):
        suggestions.append("交付前生成并附上规范参考文献表。")
    if not suggestions:
        suggestions.append("按常规流程复核即可，无需额外处理。")
    for index, text in enumerate(suggestions, start=1):
        lines.append(f"{index}. {text}")

    return "\n".join(lines).strip() + "\n"


def render_references(
    sources: list[dict[str, Any]],
    style: str = "plain",
    include_uncited: bool = True,
    heading: str = "## 参考文献",
) -> str:
    """Render an ordered reference list from the audit's source rows."""
    rows = [row for row in sources if include_uncited or row.get("cited")]
    if not rows:
        return f"{heading}\n\n（本次研究没有可用的来源记录）\n"

    lines = [heading, ""]
    for index, row in enumerate(rows, start=1):
        title = (row.get("title") or "").strip() or urls.domain(row.get("url", "")) or "未命名来源"
        url = row.get("url", "")
        if row.get("kind") == "local":
            lines.append(f"[{index}] [本地文献] {title}. 本地资料库. {url}")
            continue
        if style == "gbt7714-lite":
            lines.append(f"[{index}] {title}[EB/OL]. {url}.")
        else:
            lines.append(f"[{index}] {title}. {urls.domain(url)}. {url}")
    return "\n".join(lines).strip() + "\n"
