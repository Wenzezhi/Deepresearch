# 确定性演示（报告质检）

外网模型/搜索不稳定时，用本地 mock 让**真实研究流程**跑通，再用质检功能审计它产出的报告。
演示数据不是硬编码进数据库的：研究记录由后端流程真实生成（规划 → 检索 → 任务总结 → 报告），
只是模型与搜索换成本地 mock，保证可重复。

## 启动

```powershell
# 1) mock 搜索（SearXNG 兼容，端口 8888）
backend\.venv\Scripts\python.exe -m uvicorn tools.demo.mock_searxng_server:app --host 127.0.0.1 --port 8888

# 2) mock 模型（OpenAI 兼容，端口 8099）
backend\.venv\Scripts\python.exe -m uvicorn tools.demo.mock_llm_server:app --host 127.0.0.1 --port 8099

# 3) backend/.env 里设置并重启后端
#    SEARCH_API=searxng
#    SEARXNG_URL=http://127.0.0.1:8888
#    FETCH_FULL_PAGE=False

# 4) 跑一次真实研究并输出演示 run id
backend\.venv\Scripts\python.exe tools\demo\pipeline_demo.py
```

打开 http://127.0.0.1:5174 ，在历史记录里找到刚生成的「多模态大模型在 2025 年的关键突破」，
点报告右上角「质检」即可看到指标、问题清单、引用位置与质检单。

## 说明

- mock 模型返回固定但结构化合理的内容；mock 搜索返回 6 条可核验来源。
- 报告里故意包含 1 条编造链接、重复引用与一处无行内引用章节，用于演示质检命中。
- 演示结束后，若要做真实研究，把 `.env` 里的 `SEARCH_API` 改回 `duckduckgo`/`tavily` 并重启后端。
