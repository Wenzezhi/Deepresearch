"""Parse a research report and its source list without touching the app models."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from . import urls

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_MD_LINK = re.compile(
    r"\[(?P<text>[^\]\n]{0,200})\]\(\s*<?(?P<url>(?:https?://|local://)[^)\s>]+)>?\s*\)"
)
_BULLET_SOURCE = re.compile(
    r"^\s{0,3}[-*+]\s+(?P<label>.+?)\s*(?:[:：]|[—–]{1,2}|(?<=\s)-(?=\s))\s*"
    r"(?P<url>(?:https?://|local://)[^\s<>\"'）)，。；]+)\s*$"
)
_SOURCE_LINE = re.compile(
    r"^\s{0,3}[-*+]\s+(?P<label>.+?)\s*(?:[:：]|[—–]{1,2}|(?<=\s)-(?=\s))\s*"
    r"(?P<url>\S+)\s*$"
)
_BARE_URL = re.compile(r"https?://[^\s<>\"'()\[\]{}，。；、）】]+")
_LOCAL_REF = re.compile(r"local://documents/[A-Za-z0-9:_-]+")
_LOCAL_LABEL = re.compile(r"^\[[^\]]*本地文献[^\]]*\]\s*")

REFERENCE_HEADING = re.compile(r"参考(?:来源|文献|资料)|参考来源|References?", re.I)


@dataclass
class Section:
    """One markdown heading and its body."""

    heading: str
    level: int
    line_start: int
    line_end: int
    body: str = ""
    is_reference: bool = False

    @property
    def body_length(self) -> int:
        return len(self.body.strip())


@dataclass
class Citation:
    url: str
    normalized: str
    text: str
    section: str
    line: int
    form: str  # markdown | bullet | bare | local
    snippet: str = ""  # 该引用所在行的原文片段，用于在正文中定位
    quote: str = ""  # 该引用所在的可见句子（去掉 markdown 标记），用于句中定位

    @property
    def is_local(self) -> bool:
        return urls.is_local(self.url)


@dataclass
class Source:
    title: str
    url: str
    normalized: str
    kind: str  # web | local
    task_ids: list[int] = field(default_factory=list)

    @property
    def domain(self) -> str:
        return urls.domain(self.url)


def _clean_label(label: str) -> str:
    label = label.strip().strip("*_`")
    label = _LOCAL_LABEL.sub("", label)
    return label.strip() or "未命名来源"


_SENTENCE_BOUNDARIES = "。！？；!?;"


def visible_line(line: str) -> str:
    """Approximate the text a reader sees after markdown rendering."""
    visible = _MD_LINK.sub(lambda match: match.group("text"), line)
    visible = re.sub(r"(\*\*|__|`|\*)", "", visible)
    return visible


def sentence_at(visible: str, needle: str) -> str:
    """Return the sentence inside ``visible`` that contains ``needle``."""
    if not needle:
        return visible.strip()
    index = visible.find(needle)
    if index < 0:
        return visible.strip()
    left = 0
    for position in range(index - 1, -1, -1):
        if visible[position] in _SENTENCE_BOUNDARIES or visible[position] == "\n":
            left = position + 1
            break
    right = len(visible)
    for position in range(index + len(needle), len(visible)):
        if visible[position] in _SENTENCE_BOUNDARIES:
            right = position + 1
            break
    return visible[left:right].strip()


def source_signature(title: str, url: str) -> str:
    return f"{title.strip()}|{url.strip()}"


def _fence_mask(lines: list[str]) -> list[bool]:
    """Return True for lines inside (or delimiting) fenced code blocks."""
    mask: list[bool] = []
    inside = False
    for line in lines:
        if _FENCE.match(line):
            mask.append(True)
            inside = not inside
            continue
        mask.append(inside)
    return mask


def split_sections(markdown: str) -> list[Section]:
    """Split a report into heading sections; text before the first heading is kept."""
    lines = markdown.splitlines()
    mask = _fence_mask(lines)
    sections: list[Section] = []
    current = Section(heading="", level=0, line_start=0, line_end=len(lines))
    body: list[str] = []

    for index, line in enumerate(lines):
        if mask[index] and _FENCE.match(line):
            body.append(line)
            continue
        heading = None if mask[index] else _HEADING.match(line)
        if heading:
            current.body = "\n".join(body)
            current.line_end = index
            if current.heading or current.body.strip():
                sections.append(current)
            title = heading.group(2).strip()
            current = Section(
                heading=title,
                level=len(heading.group(1)),
                line_start=index,
                line_end=len(lines),
                is_reference=bool(REFERENCE_HEADING.search(title)),
            )
            body = []
            continue
        body.append(line)

    current.body = "\n".join(body)
    current.line_end = len(lines)
    if current.heading or current.body.strip():
        sections.append(current)
    return sections


def parse_sources(text: str, task_id: int | None = None) -> list[Source]:
    """Parse ``* title : url`` / ``- title — url`` source lists."""
    found: list[Source] = []
    if not text:
        return found
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SOURCE_LINE.match(line)
        if not match:
            continue
        url = match.group("url").strip().rstrip(".,;，。；")
        if not urls.is_http(url) and not urls.is_local(url):
            continue
        kind = "local" if urls.is_local(url) else "web"
        source = Source(
            title=_clean_label(match.group("label")),
            url=url,
            normalized=urls.normalize(url),
            kind=kind,
            task_ids=[task_id] if task_id is not None else [],
        )
        found.append(source)
    return found


def merge_sources(items: Iterable[Source]) -> list[Source]:
    """Merge duplicate sources, keeping first title and all task ids."""
    merged: dict[str, Source] = {}
    for item in items:
        key = item.normalized or url_key(item.url)
        existing = merged.get(key)
        if existing is None:
            merged[key] = Source(
                title=item.title,
                url=item.url,
                normalized=item.normalized,
                kind=item.kind,
                task_ids=list(item.task_ids),
            )
            continue
        for task_id in item.task_ids:
            if task_id not in existing.task_ids:
                existing.task_ids.append(task_id)
    return list(merged.values())


def url_key(url: str) -> str:
    return urls.normalize(url) or url


def extract_citations(markdown: str) -> list[Citation]:
    """Extract every citation-like URL from a report, with its section."""
    lines = markdown.splitlines()
    mask = _fence_mask(lines)
    citations: list[Citation] = []
    section_titles = [""]

    for index, line in enumerate(lines):
        if mask[index]:
            continue
        heading = _HEADING.match(line)
        if heading:
            section_titles.append(heading.group(2).strip())
            continue
        section = section_titles[-1]
        remainder = line
        visible = visible_line(line)

        for match in _MD_LINK.finditer(line):
            url = match.group("url").strip()
            label = match.group("text").strip()
            citations.append(
                Citation(url, urls.normalize(url), label,
                         section, index, "local" if urls.is_local(url) else "markdown",
                         quote=sentence_at(visible, label) if label else url)
            )
        remainder = _MD_LINK.sub(" ", remainder)

        bullet = _BULLET_SOURCE.match(remainder)
        if bullet:
            url = bullet.group("url").strip().rstrip(".,;，。；")
            label = _clean_label(bullet.group("label"))
            citations.append(
                Citation(url, urls.normalize(url), label,
                         section, index, "local" if urls.is_local(url) else "bullet",
                         quote=label or url)
            )
            remainder = remainder.replace(bullet.group("url"), " ")

        for match in _BARE_URL.finditer(remainder):
            url = match.group(0).rstrip(".,;，。；")
            citations.append(
                Citation(url, urls.normalize(url), "", section, index, "bare",
                         quote=sentence_at(visible, url) or url)
            )

        for match in _LOCAL_REF.finditer(remainder):
            url = match.group(0)
            if not any(c.url == url and c.line == index for c in citations):
                citations.append(
                    Citation(url, urls.normalize(url), "", section, index, "local",
                             quote=sentence_at(visible, url) or "")
                )

    for citation in citations:
        if 0 <= citation.line < len(lines):
            citation.snippet = lines[citation.line].strip()[:160]
    return citations


def section_for_line(sections: list[Section], line: int) -> Section | None:
    for section in sections:
        if section.line_start <= line < max(section.line_end, line + 1):
            return section
    return None


def line_offsets(markdown: str) -> list[str]:
    return markdown.splitlines()
