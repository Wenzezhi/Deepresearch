"""Orchestrator coordinating the deep research workflow."""

from __future__ import annotations

import logging
import re
from time import perf_counter
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Callable, Iterator

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
from services.llm import ResearchLLM, ModelOutputError, require_text
from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool

from config import Configuration
from prompts import (
    report_writer_instructions,
    task_summarizer_instructions,
    todo_planner_system_prompt,
)
from models import SummaryState, SummaryStateOutput, TodoItem
from services.planner import PlanningService
from services.reporter import ReportingService
from services.search import dispatch_search, prepare_research_context, _safe_error
from services.summarizer import SummarizationService
from services.tool_events import ToolCallTracker

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """Coordinator orchestrating TODO-based research workflow using HelloAgents."""

    def __init__(self, config: Configuration | None = None) -> None:
        """Initialise the coordinator with configuration and shared tools."""
        self.config = config or Configuration.from_env()
        self.llm = self._init_llm()

        self.note_tool = (
            NoteTool(workspace=self.config.notes_workspace)
            if self.config.enable_notes
            else None
        )
        self.tools_registry: ToolRegistry | None = None
        if self.note_tool:
            registry = ToolRegistry()
            registry.register_tool(self.note_tool)
            self.tools_registry = registry

        self._tool_tracker = ToolCallTracker(
            self.config.notes_workspace if self.config.enable_notes else None
        )
        self._tool_event_sink_enabled = False
        self._state_lock = Lock()

        self.todo_agent = self._create_tool_aware_agent(
            name="研究规划专家",
            system_prompt=todo_planner_system_prompt.strip(),
        )
        self.report_agent = self._create_tool_aware_agent(
            name="报告撰写专家",
            system_prompt=report_writer_instructions.strip(),
        )

        self._summarizer_factory: Callable[[], ToolAwareSimpleAgent] = lambda: self._create_tool_aware_agent(  # noqa: E501
            name="任务总结专家",
            system_prompt=task_summarizer_instructions.strip(),
        )

        self.planner = PlanningService(self.todo_agent, self.config)
        self.summarizer = SummarizationService(self._summarizer_factory, self.config)
        self.reporting = ReportingService(self.report_agent, self.config)
        self._last_search_notices: list[str] = []
        # 本地文献库
        self.document_library = None

        # 本次研究选中的文献 ID
        self.local_document_ids: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def _init_llm(self) -> HelloAgentsLLM:
        """Instantiate HelloAgentsLLM following configuration preferences."""
        llm_kwargs: dict[str, Any] = {"temperature": 0.0, "max_tokens": self.config.llm_max_tokens, "timeout": self.config.llm_timeout}

        model_id = self.config.llm_model_id or self.config.local_llm
        if model_id:
            llm_kwargs["model"] = model_id

        provider = (self.config.llm_provider or "").strip()
        if provider:
            llm_kwargs["provider"] = provider

        if provider == "ollama":
            llm_kwargs["base_url"] = self.config.sanitized_ollama_url()
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif provider == "lmstudio":
            llm_kwargs["base_url"] = self.config.lmstudio_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
        else:
            if self.config.llm_base_url:
                llm_kwargs["base_url"] = self.config.llm_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key

        return ResearchLLM(**llm_kwargs)

    def _create_tool_aware_agent(self, *, name: str, system_prompt: str) -> ToolAwareSimpleAgent:
        """Instantiate a ToolAwareSimpleAgent sharing tool registry and tracker."""
        return ToolAwareSimpleAgent(
            name=name,
            llm=self.llm,
            system_prompt=system_prompt,
            enable_tool_calling=self.tools_registry is not None,
            tool_registry=self.tools_registry,
            tool_call_listener=self._tool_tracker.record,
        )

    def _set_tool_event_sink(self, sink: Callable[[dict[str, Any]], None] | None) -> None:
        """Enable or disable immediate tool event callbacks."""
        self._tool_event_sink_enabled = sink is not None
        self._tool_tracker.set_event_sink(sink)

    def run(self, topic: str) -> SummaryStateOutput:
        """Execute the research workflow and return the final report."""
        state = SummaryState(research_topic=topic)
        state.todo_items = self.planner.plan_todo_list(state)
        self._drain_tool_events(state)

        if not state.todo_items:
            logger.info("No TODO items generated; falling back to single task")
            state.todo_items = [self.planner.create_fallback_task(state)]

        for task in state.todo_items:
            try:
                for _ in self._execute_task(state, task, emit_stream=False):
                    pass
            except Exception as exc:
                task.status = "failed"
                task.error = _safe_error(exc)
                task.notices.append(task.error)

        if not any(task.status == "completed" for task in state.todo_items):
            return SummaryStateOutput(
                running_summary="未获得有效研究资料，未生成报告。",
                report_markdown="", todo_items=state.todo_items,
            )
        report = self.reporting.generate_report(state)
        self._drain_tool_events(state)
        state.structured_report = report
        state.running_summary = report
        self._persist_final_report(state, report)

        return SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=state.todo_items,
        )

    def run_stream(self, topic: str) -> Iterator[dict[str, Any]]:
        """Execute the workflow yielding incremental progress events."""
        state = SummaryState(research_topic=topic)
        logger.debug("Starting streaming research: topic=%s", topic)
        yield {"type": "status", "message": "初始化研究流程"}

        yield {"type": "phase", "phase": "planning", "status": "started"}
        query_failures = []
        seed = getattr(self, 'resume_tasks', None)
        if seed is None:
            state.todo_items = self.planner.plan_todo_list(state)
        else:
            state.todo_items = [TodoItem(**{k:v for k,v in t.items() if k in TodoItem.__dataclass_fields__}) for t in seed]
            for task in state.todo_items:
                if self._cancelled(): return
                if task.status == 'pending' and not task.query:
                    try:
                        task.query = self.llm.invoke([{'role':'system','content':'根据研究主题、任务标题和研究要求，生成一条适合网络搜索的查询。只输出搜索查询，不输出解释。'}, {'role':'user','content':f'研究主题：{topic}\n任务标题：{task.title}\n研究要求：{task.intent}'}]).strip()
                    except Exception as exc:
                        if self._cancelled(): return
                        task.status='failed';task.error='搜索词生成失败：'+_safe_error(exc)
                        query_failures.append(task)
        if self._cancelled(): return
        yield {"type": "phase", "phase": "planning", "status": "finished"}
        for event in self._drain_tool_events(state, step=0):
            yield event
        if not state.todo_items:
            state.todo_items = [self.planner.create_fallback_task(state)]

        channel_map: dict[int, dict[str, Any]] = {}
        for index, task in enumerate(state.todo_items, start=1):
            token = f"task_{task.id}"
            task.stream_token = token
            channel_map[task.id] = {"step": index, "token": token}

        yield {
            "type": "todo_list",
            "tasks": [self._serialize_task(t) for t in state.todo_items],
            "step": 0,
        }

        for task in query_failures:
            yield {'type':'task_status','task_id':task.id,'status':'failed','detail':task.error}

        event_queue: Queue[dict[str, Any]] = Queue()

        def enqueue(
            event: dict[str, Any],
            *,
            task: TodoItem | None = None,
            step_override: int | None = None,
        ) -> None:
            payload = dict(event)
            target_task_id = payload.get("task_id")
            if task is not None:
                target_task_id = task.id
                payload["task_id"] = task.id

            channel = channel_map.get(target_task_id) if target_task_id is not None else None
            if channel:
                payload.setdefault("step", channel["step"])
                payload["stream_token"] = channel["token"]
            if step_override is not None:
                payload["step"] = step_override
            event_queue.put(payload)

        def tool_event_sink(event: dict[str, Any]) -> None:
            enqueue(event)

        self._set_tool_event_sink(tool_event_sink)

        threads: list[Thread] = []

        def worker(task: TodoItem, step: int) -> None:
            try:
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "in_progress",
                        "title": task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                    },
                    task=task,
                )

                for event in self._execute_task(state, task, emit_stream=True, step=step):
                    enqueue(event, task=task)
            except Exception as exc:  # pragma: no cover - defensive guardrail
                task.status = "failed"
                task.error = _safe_error(exc)
                task.notices.append(task.error)
                logger.error("Task %s failed: %s", task.id, task.error)
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "failed",
                        "detail": task.error,
                        "title": task.title,
                        "intent": task.intent,
                        "note_id": task.note_id,
                        "note_path": task.note_path,
                    },
                    task=task,
                )
            finally:
                enqueue({"type": "__task_done__", "task_id": task.id})

        yield {"type": "phase", "phase": "execution", "status": "started"}
        for task in state.todo_items:
            if self._cancelled(): break
            if task.status != 'pending': continue
            step = channel_map.get(task.id, {}).get("step", 0)
            thread = Thread(target=worker, args=(task, step), daemon=True)
            threads.append(thread)
            thread.start()

        active_workers = len(threads)
        finished_workers = 0

        try:
            while finished_workers < active_workers:
                if self._cancelled(): return
                try: event = event_queue.get(timeout=.2)
                except Empty: continue
                if event.get("type") == "__task_done__":
                    finished_workers += 1
                    continue
                yield event

            while True:
                try:
                    event = event_queue.get_nowait()
                except Empty:
                    break
                if event.get("type") != "__task_done__":
                    yield event
        finally:
            self._set_tool_event_sink(None)
            for thread in threads:
                if not self._cancelled(): thread.join()

        if self._cancelled(): return
        yield {"type": "phase", "phase": "execution", "status": "finished"}
        if not any(task.status == "completed" for task in state.todo_items):
            yield {"type": "error", "detail": "所有子任务均失败或没有搜索结果，未生成报告。请查看各任务的系统提示。"}
            yield {"type": "done"}
            return
        yield {"type": "phase", "phase": "report", "status": "started"}
        report_failed = False
        try:
            report = self.reporting.generate_report(state)
        except ModelOutputError as exc:
            report_failed = True
            logger.error("Final report failed: %s", exc)
            yield {"type": "error", "detail": str(exc)}
        finally:
            yield {"type": "phase", "phase": "report", "status": "finished"}
        if report_failed:
            yield {"type": "done"}
            return
        if self._cancelled(): return
        final_step = len(state.todo_items) + 1
        for event in self._drain_tool_events(state, step=final_step):
            yield event
        state.structured_report = report
        state.running_summary = report

        note_event = self._persist_final_report(state, report)
        if note_event:
            yield note_event

        yield {
            "type": "final_report",
            "report": report,
            "note_id": state.report_note_id,
            "note_path": state.report_note_path,
        }
        yield {"type": "done"}

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------
    def _cancelled(self):
        token = getattr(self, 'cancel_event', None)
        return token is not None and token.is_set()

    def _execute_task(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Run search + summarization for a single task."""
        if self._cancelled(): return
        task.status = "in_progress"

        # search_started = perf_counter()
        # if emit_stream:
        #     yield {"type":"task_timing", "task_id":task.id, "phase":"search", "status":"started"}
        # try:
        #     search_result, notices, answer_text, backend = dispatch_search(
        #         task.query,
        #         self.config,
        #         state.research_loop_count,
        #     )
        # finally:
        #     if emit_stream:
        #         yield {"type":"task_timing", "task_id":task.id, "phase":"search", "status":"finished", "elapsed":perf_counter()-search_started}
        # if self._cancelled(): return
        # self._last_search_notices = notices
        # task.notices = notices
        #
        # if emit_stream:
        #     for event in self._drain_tool_events(state, step=step):
        #         yield event
        # else:
        #     self._drain_tool_events(state)
        #
        # if notices and emit_stream:
        #     for notice in notices:
        #         if notice:
        #             yield {
        #                 "type": "status",
        #                 "message": notice,
        #                 "task_id": task.id,
        #                 "step": step,
        #             }
        #
        # if not search_result or not search_result.get("results"):
        #     task.status = "skipped"
        #     task.notices.append("搜索正常结束但没有结果，此任务已跳过。")
        #     if emit_stream:
        #         for event in self._drain_tool_events(state, step=step):
        #             yield event
        #         yield {
        #             "type": "task_status",
        #             "task_id": task.id,
        #             "status": "skipped",
        #             "detail": "搜索正常结束但没有结果，此任务已跳过。",
        #             "title": task.title,
        #             "intent": task.intent,
        #             "note_id": task.note_id,
        #             "note_path": task.note_path,
        #             "step": step,
        #         }
        #     else:
        #         self._drain_tool_events(state)
        #     return
        # else:
        #     if not emit_stream:
        #         self._drain_tool_events(state)
        #
        # sources_summary, context = prepare_research_context(
        #     search_result,
        #     answer_text,
        #     self.config,
        # )
        #
        # task.sources_summary = sources_summary
        #
        # with self._state_lock:
        #     state.web_research_results.append(context)
        #     state.sources_gathered.append(sources_summary)
        #     state.research_loop_count += 1


        search_started = perf_counter()

        if emit_stream:
            yield {
                "type": "task_timing",
                "task_id": task.id,
                "phase": "search",
                "status": "started"
            }

        # ==========================================
        # 第一部分：检索本地文献
        # ==========================================

        local_hits = []
        local_context = ""
        local_sources_summary = ""

        if (
            self.document_library is not None
            and self.local_document_ids
        ):
            try:
                # 综合子任务标题、研究意图和搜索关键词
                query = " ".join(
                    part
                    for part in (
                        task.title,
                        task.intent,
                        task.query
                    )
                    if part
                )

                # 从用户选择的本地文献中检索相关内容
                local_hits = self.document_library.search(
                    query,
                    document_ids=self.local_document_ids,
                    top_k=6
                )

                # 整理检索结果和引用信息
                (
                    local_context,
                    local_sources_summary
                ) = self.document_library.format_context(
                    local_hits
                )

            except Exception as exc:

                logger.warning(
                    "Local document retrieval failed: %s",
                    _safe_error(exc)
                )

                task.notices.append(
                    "本地文献检索失败，本任务将继续使用网络资料。"
                )

        # ==========================================
        # 第二部分：检索互联网资料
        # ==========================================

        try:
            try:
                search_result, notices, answer_text, backend = dispatch_search(
                    task.query,
                    self.config,
                    state.research_loop_count,
                )

            except Exception as exc:

                # 如果网络搜索失败，但本地文献已经检索到内容，
                # 则继续使用本地文献完成研究。
                if not local_hits:
                    raise

                search_result = {"results": []}
                answer_text = None
                backend = "local-document"

                notices = [
                    f"网络检索暂不可用，已使用本地文献继续研究：{_safe_error(exc)}"
                ]

        finally:

            if emit_stream:
                yield {
                    "type": "task_timing",
                    "task_id": task.id,
                    "phase": "search",
                    "status": "finished",
                    "elapsed": perf_counter() - search_started
                }

        if self._cancelled():
            return

        self._last_search_notices = notices

        # 保留本地检索产生的提示信息
        task.notices.extend(notices)

        if local_hits:
            task.notices.append(
                f"已从 {len(self.local_document_ids)} 篇所选文献中召回 "
                f"{len(local_hits)} 段相关内容。"
            )

        # ==========================================
        # 第三部分：处理原有搜索工具事件
        # ==========================================

        if emit_stream:

            for event in self._drain_tool_events(
                state,
                step=step
            ):
                yield event

        else:
            self._drain_tool_events(state)

        if notices and emit_stream:

            for notice in notices:

                if notice:
                    yield {
                        "type": "status",
                        "message": notice,
                        "task_id": task.id,
                        "step": step,
                    }

        # ==========================================
        # 第四部分：判断是否有可用研究资料
        # ==========================================

        has_web_results = bool(
            search_result
            and search_result.get("results")
        )

        # 只有网络资料和本地资料都没有时才跳过任务
        if not has_web_results and not local_hits:

            task.status = "skipped"

            task.notices.append(
                "网络搜索没有结果，所选本地文献也未召回相关内容；此任务已跳过。"
            )

            if emit_stream:

                for event in self._drain_tool_events(
                    state,
                    step=step
                ):
                    yield event

                yield {
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "skipped",
                    "detail": "网络搜索和本地文献均未获得可用资料。",
                    "title": task.title,
                    "intent": task.intent,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                    "step": step,
                }

            else:
                self._drain_tool_events(state)

            return

        elif not emit_stream:
            self._drain_tool_events(state)

        # ==========================================
        # 第五部分：整理网络搜索资料
        # ==========================================

        sources_summary, context = prepare_research_context(
            search_result or {"results": []},
            answer_text,
            self.config,
        )

        # ==========================================
        # 第六部分：合并本地文献和网络资料
        # ==========================================

        if local_context:

            context = "\n\n".join(
                part
                for part in (
                    context,
                    local_context
                )
                if part
            )

            sources_summary = "\n".join(
                part
                for part in (
                    sources_summary,
                    local_sources_summary
                )
                if part
            )

        # 保存本任务的全部来源
        task.sources_summary = sources_summary

        # ==========================================
        # 第七部分：更新研究状态
        # ==========================================

        with self._state_lock:

            state.web_research_results.append(context)

            state.sources_gathered.append(
                sources_summary
            )

            if has_web_results:
                state.research_loop_count += 1


        summary_started = perf_counter()
        if emit_stream:
            yield {"type":"task_timing", "task_id":task.id, "phase":"summary", "status":"started"}
        try:
            summary_text: str | None = None

            if emit_stream:
                for event in self._drain_tool_events(state, step=step):
                    yield event
                yield {
                    "type": "sources",
                    "task_id": task.id,
                    "latest_sources": sources_summary,
                    "raw_context": context,
                    "step": step,
                    "backend": backend,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                }

                summary_stream, summary_getter = self.summarizer.stream_task_summary(state, task, context)
                try:
                    for event in self._drain_tool_events(state, step=step):
                        yield event
                    for chunk in summary_stream:
                        if chunk:
                            yield {
                                "type": "task_summary_chunk",
                                "task_id": task.id,
                                "content": chunk,
                                "note_id": task.note_id,
                                "step": step,
                            }
                        for event in self._drain_tool_events(state, step=step):
                            yield event
                except ModelOutputError as exc:
                    raise ModelOutputError(f"任务总结失败：{exc}") from exc
                summary_text = summary_getter()
            else:
                summary_text = self.summarizer.summarize_task(state, task, context)
                self._drain_tool_events(state)
        finally:
            if emit_stream:
                yield {"type":"task_timing", "task_id":task.id, "phase":"summary", "status":"finished", "elapsed":perf_counter()-summary_started}

        if self._cancelled(): return
        task.summary = require_text(summary_text, "任务总结")
        task.status = "completed"

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
            yield {
                "type": "task_status",
                "task_id": task.id,
                "status": "completed",
                "summary": task.summary,
                "sources_summary": task.sources_summary,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
            }
        else:
            self._drain_tool_events(state)

    def _drain_tool_events(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]:
        """Proxy to the shared tool call tracker."""
        events = self._tool_tracker.drain(state, step=step)
        if self._tool_event_sink_enabled:
            return []
        return events

    @property
    def _tool_call_events(self) -> list[dict[str, Any]]:
        """Expose recorded tool events for legacy integrations."""
        return self._tool_tracker.as_dicts()

    def _serialize_task(self, task: TodoItem) -> dict[str, Any]:
        """Convert task dataclass to serializable dict for frontend."""
        return {
            "id": task.id,
            "title": task.title,
            "intent": task.intent,
            "query": task.query,
            "status": task.status,
            "summary": task.summary,
            "error": task.error,
            "notices": task.notices,
            "sources_summary": task.sources_summary,
            "note_id": task.note_id,
            "note_path": task.note_path,
            "stream_token": task.stream_token,
        }

    def _persist_final_report(self, state: SummaryState, report: str) -> dict[str, Any] | None:
        if not self.note_tool or not report or not report.strip():
            return None

        note_title = f"研究报告：{state.research_topic}".strip() or "研究报告"
        tags = ["deep_research", "report"]
        content = report.strip()

        note_id = self._find_existing_report_note_id(state)
        response = ""

        if note_id:
            response = self.note_tool.run(
                {
                    "action": "update",
                    "note_id": note_id,
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            if response.startswith("❌"):
                note_id = None

        if not note_id:
            response = self.note_tool.run(
                {
                    "action": "create",
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            note_id = self._extract_note_id_from_text(response)

        if not note_id:
            return None

        state.report_note_id = note_id
        if self.config.notes_workspace:
            note_path = Path(self.config.notes_workspace) / f"{note_id}.md"
            state.report_note_path = str(note_path)
        else:
            note_path = None

        payload = {
            "type": "report_note",
            "note_id": note_id,
            "title": note_title,
            "content": content,
        }
        if note_path:
            payload["note_path"] = str(note_path)

        return payload

    def _find_existing_report_note_id(self, state: SummaryState) -> str | None:
        if state.report_note_id:
            return state.report_note_id

        for event in reversed(self._tool_tracker.as_dicts()):
            if event.get("tool") != "note":
                continue

            parameters = event.get("parsed_parameters") or {}
            if not isinstance(parameters, dict):
                continue

            action = parameters.get("action")
            if action not in {"create", "update"}:
                continue

            note_type = parameters.get("note_type")
            if note_type != "conclusion":
                title = parameters.get("title")
                if not (isinstance(title, str) and title.startswith("研究报告")):
                    continue

            note_id = parameters.get("note_id")
            if not note_id:
                note_id = self._tool_tracker._extract_note_id(event.get("result", ""))  # type: ignore[attr-defined]

            if note_id:
                return note_id

        return None

    @staticmethod
    def _extract_note_id_from_text(response: str) -> str | None:
        if not response:
            return None

        match = re.search(r"ID:\s*([^\n]+)", response)
        if not match:
            return None

        return match.group(1).strip()


def run_deep_research(topic: str, config: Configuration | None = None) -> SummaryStateOutput:
    """Convenience function mirroring the class-based API."""
    agent = DeepResearchAgent(config=config)
    return agent.run(topic)
