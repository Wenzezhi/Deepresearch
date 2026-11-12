"""Tiny SearXNG-compatible mock for deterministic local demos.

hello_agents 的 searxng 后端通过 GET /search?format=json 取结果，
这里返回固定的、可核验来源列表，使研究流程无需外网搜索即可跑通。
"""
from __future__ import annotations

from fastapi import FastAPI, Request

app = FastAPI(title="mock-searxng")

RESULTS = [
    {
        "title": "Native Multimodal Models: A Roadmap",
        "url": "https://arxiv.org/html/2605.25343v1",
        "content": "原生多模态架构把各模态映射到共享嵌入空间，通过统一 tokenizer 与共享 backbone 做端到端训练。",
    },
    {
        "title": "MMMU-Pro Leaderboard (LLM-Stats)",
        "url": "https://llm-stats.com/benchmarks/mmmu-pro",
        "content": "MMMU-Pro 通过视觉嵌入与选项扩展抑制记忆型作答，前沿分数集中在 0.807–0.860。",
    },
    {
        "title": "STORM: Token-Efficient Long Video Understanding",
        "url": "https://research.nvidia.com/labs/lpr/storm",
        "content": "先注入时序再做 token 压缩，STORM 报告约 8 倍 token 压缩与显著推理加速。",
    },
    {
        "title": "OSWorld: Benchmarking Computer-Use Agents",
        "url": "https://osworld-v1.xlang.ai",
        "content": "OSWorld 使用 134 个执行型评估函数，长程任务成功率仍是主要瓶颈。",
    },
    {
        "title": "Awesome Streaming Video Understanding",
        "url": "https://github.com/sotayang/Awesome-Streaming-Video-Understanding",
        "content": "实时流式视频理解需要在因果约束下决定何时输出，是比长视频更难的开放问题。",
    },
    {
        "title": "Open-Source Multimodal Models Comparison 2026",
        "url": "https://www.bentoml.com/blog/multimodal-ai-a-guide-to-open-source-vision-language-models",
        "content": "开源多模态模型在垂直感知任务上已接近闭源水平，但在推理编排上仍有差距。",
    },
]


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "mock-searxng"}


@app.get("/search")
def search(request: Request, q: str = "", format: str = "json"):  # noqa: A002
    return {
        "query": q,
        "number_of_results": len(RESULTS),
        "results": RESULTS,
        "answers": [],
        "infoboxes": [],
        "suggestions": [],
    }
