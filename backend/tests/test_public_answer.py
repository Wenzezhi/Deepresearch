import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from services.text_processing import public_answer
from services.summarizer import SummarizationService
from services.reporter import ReportingService
from services.llm import ModelOutputError
from config import Configuration
from models import SummaryState, TodoItem

class PublicAnswerTests(unittest.TestCase):
    def test_historical_rounds_keep_last_final_document(self):
        text='I will read the existing note.\n{"note_type":"task_state","content":"draft"}\n# 任务总结\n旧草稿\n现在写入笔记。然后输出总结。 ## 任务总结\n\n### 关键发现\n**最终结论**与[来源](https://example.com)。'
        self.assertEqual(public_answer(text),'## 任务总结\n\n### 关键发现\n**最终结论**与[来源](https://example.com)。')
    def test_reasoning_tags_closed_unclosed_case_insensitive(self):
        for tag in ['think','THINK','reasoning','analysis','thinking']:
            self.assertEqual(public_answer(f'<{tag}>private</{tag}># 任务总结\n结论'),'# 任务总结\n结论')
            self.assertEqual(public_answer(f'<{tag}>private'),'')
    def test_explicit_final_boundary_and_report(self):
        self.assertEqual(public_answer('internal\n<final_answer># 报告\n公开结论</final_answer>','report'),'# 报告\n公开结论')
        self.assertEqual(public_answer('<final_answer>unfinished'),'')
    def test_preserve_research_about_reasoning(self):
        body='## 任务总结\n\n推理模型与思维链是本研究的技术主题。\n\n| 技术 | 作用 |\n|---|---|\n| reasoning | 分析 |'
        self.assertEqual(public_answer(body),body)
    def test_no_final_boundary_in_work_log_is_not_public(self):
        self.assertEqual(public_answer("I'll start by reading the existing note."),'')
    def test_stream_service_uses_only_final_agent_round(self):
        agent=Mock();agent.run.return_value='<think>private</think><final_answer># 任务总结\n有效结论</final_answer>'
        service=SummarizationService(lambda:agent,Configuration())
        state=SummaryState(research_topic='测试');task=TodoItem(id=1,title='任务',intent='测试',query='test')
        chunks,get=service.stream_task_summary(state,task,'sources')
        agent.run.assert_not_called()
        self.assertEqual(list(chunks),['# 任务总结\n有效结论']);self.assertEqual(get(),'# 任务总结\n有效结论')
        agent.stream_run.assert_not_called();agent.clear_history.assert_called_once()
    def test_invalid_answer_emits_no_summary(self):
        agent=Mock();agent.run.return_value='<think>private unclosed'
        service=SummarizationService(lambda:agent,Configuration())
        chunks,get=service.stream_task_summary(SummaryState(research_topic='测试'),TodoItem(id=1,title='任务',intent='测试',query='test'),'sources')
        with self.assertRaises(ModelOutputError):next(chunks)
        agent.clear_history.assert_called_once()
    def test_report_uses_public_document(self):
        agent=Mock();agent.run.return_value='<reasoning>private</reasoning><final_answer># 报告\n研究结论</final_answer>'
        self.assertEqual(ReportingService(agent,Configuration()).generate_report(SummaryState(research_topic='测试')),'# 报告\n研究结论')

if __name__=='__main__':unittest.main()
