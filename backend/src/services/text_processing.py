"""Utility helpers for normalizing agent generated text."""

from __future__ import annotations

import re


def strip_tool_calls(text: str) -> str:
    """移除文本中的工具调用标记。"""

    if not text:
        return text

    pattern = re.compile(r"\[TOOL_CALL:[^\]]+\]")
    return pattern.sub("", text)



def public_answer(text: str, kind: str = "summary") -> str:
    """Extract the final document, never a tool-round narration or unfinished reasoning."""
    text = re.sub(r"<(think|thinking|reasoning|analysis)\b[^>]*>[\s\S]*?(?:</\1\s*>|$)", "", text or "", flags=re.I)
    answers = re.findall(r"<final_answer>([\s\S]*?)</final_answer>", text, flags=re.I)
    if answers:
        text = answers[-1]
    elif re.search(r"<final_answer>", text, flags=re.I):
        return ""
    text = strip_tool_calls(text).strip()
    if text.startswith("```markdown") and text.endswith("```"):
        text = text[len("```markdown"):-3].strip()
    if kind == "summary":
        headings = list(re.finditer(r"#{1,6}[ \t]+任务总结(?:[：:][^\n]*|[ \t]*)(?=\r?\n|$)", text))
        if headings:
            text = text[headings[-1].start():]
    else:
        heading = re.search(r"^#{1,2}[ \t]+[^\n]+", text, flags=re.M)
        if heading:
            text = text[heading.start():]
    # If no trustworthy document boundary remains, don't show an agent work log as an answer.
    process = r"(?:I'll (?:start|read|analy[sz]e)|Let me (?:read|analy[sz]e|think)|I (?:need to|will) (?:read|analy[sz]e)|我(?:先|需要|将要)(?:读取|分析|思考)|现在(?:写入|读取)笔记|Note 已读取|[\"]note_type[\"]\s*:)"
    if re.search(process, text, flags=re.I):
        return ""
    return text.strip()
