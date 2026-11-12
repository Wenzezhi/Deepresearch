# 设计文档：报告质检门禁（Report Quality Gate）

> 版本：v1.0（已实现）｜独立模块，不改动研究主流程、导出与本地文献功能

## 1. 定位

研究生成已经解决了"能不能出报告"，本功能解决"**这份报告能不能交付**"。

产品形态：报告阅读区右上角「质检」入口 → 右侧滑出面板，给出评分、问题清单、来源清单与质检单；可选**在原文中标记问题位置**（默认关闭，打开才在报告里加高亮与角标，关闭即完全恢复原样）。

## 2. 功能范围（v1）

| 能力 | 说明 |
|---|---|
| 引用可核验 | 报告里的链接是否真的来自本次检索；疑似编造单独列出 |
| 来源覆盖 | 长章节无来源、检索到但未被引用的来源 |
| 结构完整 | 缺结论段、缺局限说明、空章节、标题层级跳跃、报告过短 |
| 来源质量 | 来源过少、单一域名占比过高、任务零来源、只有本地来源 |
| 交付规范 | 缺参考文献段、参考文献段为空、链接写法混杂、链接无文字 |
| 评分与分级 | 100 分制，A/B/C/D 四档，扣分权重固定可解释 |
| 质检单 | 一键生成可附在报告后的 markdown（指标 + 问题 + 建议） |
| 规范参考文献表 | 按首次引用排序、去重、编号；支持 plain / gbt7714-lite |
| 原文标记开关 | 打开：高亮章节/段落并加角标；关闭：移除全部标记，DOM 复原 |

**明确不做**：不改写报告正文、不生成 Word、不新增数据表、不访问网络、不调用模型。

## 3. 数据来源（只读）

- `events` 中最后一次 `final_report` 的 `report`（遇到 `reset` 清空）
- `events` 中 `sources` 事件的 `latest_sources`，以及任务快照里的 `sources_summary`
  （格式实测为 `* 标题 : URL`；本地文献为 `local://documents/{id}`）
- 任务快照（`ResearchJobs.snapshot`）提供 task_id ↔ 标题
- `documents` 表提供本地文献 id 集合，用于判断"引用的本地文献是否已被删除"

不写库、不写文件；同一 run 连续调用结果一致（`generated_at` 除外）。

## 4. 接口

```
GET  /quality/audit/{run_id}
  → { run_id, topic, report_available, metrics{...}, score, grade,
      issues[], issue_summary{}, sources[], generated_at }
POST /quality/report  { run_id, style: "plain"|"gbt7714-lite", include_uncited }
  → { markdown, references_markdown, score, grade }
```

错误：`404` run 不存在；`422` style 非法。

## 5. 检查规则要点

- 引用抽取四种形态：markdown 链接、短横线来源行（`- 标题 — URL`）、裸 URL、`local://`；
  代码块内的 URL 与标题一律忽略。
- URL 归一化：去 fragment、去追踪参数（`utm_*`、`fbclid` 等）、host 小写去 `www.`、
  去尾斜杠、`http` 与 `https` 等价；`local://documents/{id}` 归一为 `local:{id}`。
- 长章节判定：正文 ≥ 200 字且该章节内零引用；标题层级 1 不计入空章节。
- 评分扣分上限按类型封顶，保证"问题很多"不会把分数直接打到 0 而无从解释。

## 6. 前端交互与开关

- 入口：`ResearchDocument.vue` 报告块 actions 槽内的「质检」按钮（唯一接线点，2 行）。
- 面板：评分环 + 4 个指标卡 + 三 tab（问题 / 来源 / 质检单）。
- **原文标记开关**（默认关闭）：
  - 打开：`QualityMarkerLayer` 在报告 DOM 上给对应标题/段落加 `rqg-flagged` 类并插入角标，
    显示"已标记 N 处"；
  - 关闭：移除全部类与角标，报告 DOM 与原始渲染一致；
  - 关闭面板同样清除标记；报告重新生成后自动按当前开关状态重标。
- 点击问题项：滚动定位到对应章节/段落并闪烁提示。
- 质检单 tab：生成后可预览、复制 Markdown（不改动报告本身）。

## 7. 隔离性清单

新增（全部新文件）：

| 文件 | 说明 |
|---|---|
| `backend/src/quality/{__init__,urls,parse,checks,engine,render}.py` | 检查引擎，纯函数 |
| `backend/src/quality_api.py` | 只读接口 |
| `backend/tests/test_quality_parse.py` / `test_quality_checks.py` / `test_quality_api.py` / `test_quality_real_report.py` | 测试 |
| `backend/tests/fixtures/quality_report_real.md` | 真实报告 fixture |
| `frontend/src/services/quality.ts` | 类型与请求 |
| `frontend/src/components/ReportQualityPanel.vue` | 质检面板 |
| `frontend/src/components/QualityMarkerLayer.ts` | 原文标记图层 |

修改（合计 4 行）：

| 文件 | 改动 |
|---|---|
| `backend/src/main.py` | +2 行：import + include_router |
| `frontend/src/components/ResearchDocument.vue` | +2 行：import + 入口组件 |

不触碰：`storage.py`、`agent.py`、`planner.py`、`reporter.py`、`summarizer.py`、`search.py`、
`export_api.py`、`document_api.py`、`services/document_library.py`、`MarkdownDocument.vue`、`App.vue`。

## 8. 验收（已执行）

| 项 | 结果 |
|---|---|
| 单元测试 | 48 项全绿（解析 / 检查 / 引擎 / 渲染 / 真实报告） |
| API 测试 | 7 项全绿（正常、404、无报告、非法 style、幂等、不写事件） |
| 真实报告 | 26 条引用、25 条可核验、1 条注入的编造链接被抓到；评分 66 / C |
| 既有回归 | 后端 97 项原有测试全绿 |
| 前端 | `vue-tsc --noEmit && vite build` 通过（91 模块） |
| 只读性 | 审计前后事件数不变（测试断言） |

## 9. 后续（v1.1 候选）

- 原文标记支持"永久标记"与"按严重级过滤"（当前为打开/关闭 + 定位闪烁）
- 链接可达性检查（HEAD，best-effort，标注"网络不可达"而非"失效"）
- 在正文中插入 `[n]` 编号（规则替换，不改写语义）
- 质检结果纳入导出流程（导出前提示评分与问题数）
