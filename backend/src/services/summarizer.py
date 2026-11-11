"""Task summarization utilities."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Tuple

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState, TodoItem
from config import Configuration
from services.notes import build_note_guidance
from services.text_processing import public_answer
from services.llm import require_text


class SummarizationService:
    """Handles synchronous and streaming task summarization."""

    def __init__(
        self,
        summarizer_factory: Callable[[], ToolAwareSimpleAgent],
        config: Configuration,
    ) -> None:
        self._agent_factory = summarizer_factory
        self._config = config

    def summarize_task(self, state: SummaryState, task: TodoItem, context: str) -> str:
        """Generate a task-specific summary using the summarizer agent."""

        prompt = self._build_prompt(state, task, context)

        agent = self._agent_factory()
        try:
            response = agent.run(prompt)
        finally:
            agent.clear_history()

        return require_text(public_answer(response or "", "summary"), "任务总结")

    def stream_task_summary(
        self, state: SummaryState, task: TodoItem, context: str
    ) -> Tuple[Iterator[str], Callable[[], str]]:
        """Keep tool rounds private and publish only the validated final answer.

        ToolAwareSimpleAgent.stream_run yields narration from every tool round.
        Its run method returns only the final round, while retaining tool callbacks.
        Progress and tool records still flow through the existing event tracker.
        """
        summary = ""

        def generator() -> Iterator[str]:
            nonlocal summary
            summary = self.summarize_task(state, task, context)
            yield summary

        def get_summary() -> str:
            return require_text(summary, "任务总结")

        return generator(), get_summary

    def _build_prompt(self, state: SummaryState, task: TodoItem, context: str) -> str:
        """Construct the summarization prompt shared by both modes."""

        return (
            f"任务主题：{state.research_topic}\n"
            f"任务名称：{task.title}\n"
            f"任务目标：{task.intent}\n"
            f"检索查询：{task.query}\n"
            f"任务上下文：\n{context}\n"
            f"{build_note_guidance(task)}\n"
            "引用要求：如果上下文包含 [D-xxxxxxxx] 形式的本地文献编号，"
            "涉及该文献支持的事实或观点时，请在对应句末保留该编号；"
            "页码信息可一并标注。"
            "不得虚构文献结论、页码或引用。网络来源仍需保留原始链接。\n"
            "请先完成笔记同步，最终回复只输出 <final_answer> 与 </final_answer> 包裹的正式 Markdown 总结，以 # 任务总结 开头。不得包含推理过程、工作计划、工具参数或笔记原始 JSON。"
        )
