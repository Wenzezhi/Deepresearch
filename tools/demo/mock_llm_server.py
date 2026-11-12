"""Deterministic OpenAI-compatible mock used only for local end-to-end demos.

它让研究流程真实跑通（规划 → 检索 → 任务总结 → 报告），
但把模型输出固定下来，方便在没有稳定外网模型时演示质检功能。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="mock-research-llm")

SOURCE_LINE = re.compile(r"^\s*[*\-]\s*(?P<title>.+?)\s*:\s*(?P<url>https?://\S+)\s*$", re.M)
TOPIC_LINE = re.compile(r"研究主题：(.+)")


def _last_user_text(body: dict[str, Any]) -> str:
    for message in reversed(body.get("messages") or []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
    return ""


def _plan() -> str:
    tasks = [
        {"title": "任务 1: 架构路线梳理",
         "intent": "梳理原生多模态架构的路线与代表工作",
         "query": "native multimodal architecture 2025"},
        {"title": "任务 2: 评测基准对比",
         "intent": "对比 MMMU-Pro 等评测基准的演进与局限",
         "query": "MMMU-Pro benchmark leaderboard"},
        {"title": "任务 3: 长视频理解",
         "intent": "总结长视频理解的关键技术与 token 压缩方案",
         "query": "long video understanding token compression"},
        {"title": "任务 4: 智能体现状",
         "intent": "整理计算机使用智能体的能力与失败模式",
         "query": "computer use agent OSWorld benchmark"},
    ]
    return json.dumps({"tasks": tasks}, ensure_ascii=False)


def _summary(prompt: str) -> str:
    urls = [match.group("url") for match in SOURCE_LINE.finditer(prompt)]
    cite = "、".join(urls[:2]) if urls else "（无网络来源）"
    return (
        "# 任务总结\n\n"
        "## 主要发现\n\n"
        f"- 该任务检索到 {len(urls)} 条来源，核心结论以来源原文为准。\n"
        "- 2025 年的主线是架构从 late-fusion 走向原生统一，评测则转向反污染设计。\n"
        f"- 关键来源：{cite}\n\n"
        "## 证据与缺口\n\n"
        "- 证据多为厂商与基准页面，缺少独立复现。\n"
        "- 长视频与智能体方向的口径差异较大，需要在报告中降级表述。\n"
    )


def _report(prompt: str) -> str:
    topic_match = TOPIC_LINE.search(prompt)
    topic = (topic_match.group(1).strip().splitlines()[0] if topic_match else "多模态大模型研究").strip()
    sources = []
    seen = set()
    for match in SOURCE_LINE.finditer(prompt):
        url = match.group("url")
        if url in seen:
            continue
        seen.add(url)
        sources.append((match.group("title").strip(), url))

    # 规范写法：正文用 [n] 编号引用，URL 只出现在文末参考文献表
    blocks = [
        f"# {topic}",
        "",
        "## 一、背景概览",
        "",
        f"2025 年，多模态大模型的主线从「模态拼接」转向「原生统一」[1]。"
        "评测体系同步转向反污染设计，随机猜测基线被显著压低[2]。",
        "",
        "## 二、核心发现",
        "",
        "1. **架构**：原生统一架构在同等算力下不劣于 late-fusion，代表性路线见 [1]。",
        "2. **评测**：MMMU-Pro 通过视觉嵌入与选项扩展抑制记忆型作答，"
        "前沿分数集中在 0.807–0.860[2]。",
        "3. **长视频**：先注入时序再压缩 token 的路线收益最稳，缺少时序编码时"
        "单纯压缩会收益递减[3]。",
        "4. **智能体**：短任务成功率已较高，但长程任务的效率与恢复能力仍是瓶颈[4]；"
        "另一项长程评测显示，最佳系统在长任务上的成功率仍低于 25%[9]。",
        "",
        "## 三、风险与局限",
        "",
        "本研究的数据主要来自厂商博客、榜单页面与二手解读，独立复现实验的数量有限，"
        "因此结论更适合作为选型参考而不是性能定论。不同任务的评测口径差异较大，"
        "榜单分数与实际业务效果之间可能存在明显偏差，需要在落地前用自有数据复核。"
        "另外，部分来源的发布时间距今较久，时效性需要在采用时再次确认；"
        "对于长视频与智能体方向，公开基准的覆盖度仍不足以支撑强结论，"
        "建议在报告中保留不确定性描述，并在后续研究中补充小规模验证实验。"
        "总体而言，本报告的价值在于梳理主线与风险清单，而不是给出确定性的性能排名。",
        "",
        "## 四、结论",
        "",
        "2025 年的关键变化是架构范式与评测方法同时收敛[1]；"
        "落地时应优先核对来源可信度与评测口径，再决定技术路线。",
        "",
        "## 参考文献",
        "",
    ]
    for index, (title, url) in enumerate(sources, start=1):
        domain = url.split("/")[2] if "//" in url else ""
        blocks.append(f"[{index}] {title}. {domain}. {url}")
    # 一条"检索结果里没有"的参考文献，用于演示未核验检测
    blocks.append(
        f"[{len(sources) + 1}] A Survey of Long-Horizon Computer-Use Agents. arxiv.org. "
        "https://fabricated.example.org/paper"
    )
    blocks.append("")
    return "\n".join(blocks)


def _answer(prompt: str) -> str:
    if "任务概览：" in prompt and "任务笔记" in prompt:
        return f"<final_answer>\n{_report(prompt)}\n</final_answer>"
    if "任务名称：" in prompt:
        return f"<final_answer>\n{_summary(prompt)}\n</final_answer>"
    if "研究主题" in prompt and "任务" in prompt and "JSON" in prompt.upper():
        return _plan()
    if "研究主题" in prompt:
        return _plan()
    return "OK"


def _chunks(text: str, size: int = 120):
    for start in range(0, len(text), size):
        yield text[start:start + size]


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "mock-research-llm"}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "mock-research", "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    prompt = _last_user_text(body)
    content = _answer(prompt)
    model = body.get("model") or "mock-research"
    created = int(time.time())

    if not body.get("stream"):
        return JSONResponse({
            "id": f"chatcmpl-mock-{created}",
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": max(1, len(prompt) // 4),
                "completion_tokens": max(1, len(content) // 4),
                "total_tokens": max(2, (len(prompt) + len(content)) // 4),
            },
        })

    def event_stream():
        yield (
            "data: " + json.dumps({
                "id": f"chatcmpl-mock-{created}",
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }, ensure_ascii=False) + "\n\n"
        )
        for piece in _chunks(content):
            yield (
                "data: " + json.dumps({
                    "id": f"chatcmpl-mock-{created}",
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
                }, ensure_ascii=False) + "\n\n"
            )
        yield (
            "data: " + json.dumps({
                "id": f"chatcmpl-mock-{created}",
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": max(1, len(prompt) // 4),
                    "completion_tokens": max(1, len(content) // 4),
                    "total_tokens": max(2, (len(prompt) + len(content)) // 4),
                },
            }, ensure_ascii=False) + "\n\n"
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
