import json
import sys
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
import httpx
from openai import OpenAI
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from services.llm import ResearchLLM, ModelOutputError, EmptyModelOutputError


def completion(content='', reason='stop', reasoning=None):
    message={'role':'assistant','content':content}
    if reasoning is not None:message['reasoning_content']=reasoning
    return {'id':'test','object':'chat.completion','created':0,'model':'test',
            'choices':[{'index':0,'message':message,'finish_reason':reason}],
            'usage':{'prompt_tokens':10,'completion_tokens':734,'total_tokens':744}}


class RecoveryTests(unittest.TestCase):
    def client(self, outcomes):
        self.calls=[]
        def handle(request):
            self.calls.append(json.loads(request.content))
            result=outcomes[min(len(self.calls)-1,len(outcomes)-1)]
            if result=='timeout':raise httpx.ReadTimeout('test',request=request)
            if isinstance(result,int):return httpx.Response(result,json={'error':{'message':'test'}})
            if isinstance(result,bytes):return httpx.Response(200,content=result,headers={'content-type':'text/event-stream'})
            return httpx.Response(200,json=result)
        client=OpenAI(api_key='private-test-key',base_url='https://example.test/v1',http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        self.addCleanup(client.close)
        return client

    def llm(self,outcomes):
        client=self.client(outcomes)
        with patch('hello_agents.core.llm.OpenAI',return_value=client):
            model=ResearchLLM(model='test',provider='custom',api_key='private-test-key',base_url='https://example.test/v1')
        self.assertEqual(model._client.max_retries,0)
        return model

    @patch('services.llm.time.sleep')
    def test_empty_then_body_preserves_input_and_hides_reasoning(self,_):
        llm=self.llm([completion(None,reasoning='private reasoning'),completion('# 正式报告')])
        messages=[{'role':'user','content':'private prompt'}]
        with self.assertLogs('services.llm',level='INFO') as logs:
            self.assertEqual(llm.invoke(messages),'# 正式报告')
        self.assertEqual(len(self.calls),2);self.assertEqual(len(messages),1)
        self.assertEqual(self.calls[1]['messages'][0],messages[0])
        self.assertIn('has_reasoning=True',str(logs.output))
        for private in ('private reasoning','private prompt','private-test-key'):self.assertNotIn(private,str(logs.output))

    @patch('services.llm.time.sleep')
    def test_mixed_failures_share_four_attempts(self,_):
        llm=self.llm(['timeout',completion(''),503,completion(''),completion('should not be requested')])
        with self.assertRaisesRegex(EmptyModelOutputError,'共 4 次请求'):llm.invoke([])
        self.assertEqual(len(self.calls),4)

    @patch('services.llm.time.sleep')
    def test_four_empty_responses_stop(self,_):
        llm=self.llm([completion(' ')])
        with self.assertRaisesRegex(EmptyModelOutputError,'最多 3 次重试'):llm.invoke([])
        self.assertEqual(len(self.calls),4)

    @patch('services.llm.time.sleep')
    def test_reasoning_only_is_not_a_report(self,_):
        llm=self.llm([completion('<think>private reasoning</think>'),completion('# Report')])
        self.assertEqual(llm.invoke([]),'# Report');self.assertEqual(len(self.calls),2)

    @patch('services.llm.time.sleep')
    def test_tool_call_text_remains_valid(self,_):
        tool='[TOOL_CALL:note:{"action":"read","note_id":"n1"}]'
        llm=self.llm([completion(tool)]);self.assertEqual(llm.invoke([]),tool);self.assertEqual(len(self.calls),1)

    @patch('services.llm.time.sleep')
    def test_length_and_filter_do_not_retry(self,_):
        for reason in ('length','content_filter'):
            llm=self.llm([completion('',reason)])
            with self.assertRaises(ModelOutputError):llm.invoke([])
            self.assertEqual(len(self.calls),1)

    def test_cancel_during_backoff_stops_retry(self):
        llm=self.llm([completion('')]);cancel=Event();llm.cancel_event=cancel
        def stop(delay):cancel.set();return True
        with patch.object(cancel,'wait',side_effect=stop):
            with self.assertRaisesRegex(ModelOutputError,'研究已暂停'):llm.invoke([])
        self.assertEqual(len(self.calls),1)

    @patch('services.llm.time.sleep')
    def test_empty_stream_retries_without_duplicate_text(self,_):
        def stream(content):
            data={'id':'s','object':'chat.completion.chunk','created':0,'model':'test','choices':[{'index':0,'delta':{'content':content},'finish_reason':'stop'}]}
            return ('data: '+json.dumps(data)+'\n\ndata: [DONE]\n\n').encode()
        llm=self.llm([stream(''),stream('正文')])
        self.assertEqual(''.join(llm.stream_invoke([])),'正文');self.assertEqual(len(self.calls),2)

    @patch('agent.dispatch_search')
    @patch('services.llm.time.sleep')
    def test_completed_tasks_resume_report_and_recover_empty_response(self,_,search):
        from agent import DeepResearchAgent
        from config import Configuration
        client=self.client([completion('',reasoning='private'),completion('<final_answer># 最终报告\n\n保留已有成果。</final_answer>')])
        with patch('hello_agents.core.llm.OpenAI',return_value=client):
            agent=DeepResearchAgent(Configuration(llm_provider='custom',llm_model_id='test',llm_api_key='test',llm_base_url='https://example.test/v1',enable_notes=False))
        saved={'id':1,'title':'成功任务','intent':'研究要求','query':'query','status':'completed','summary':'保留已有成果','sources_summary':'来源'}
        agent.resume_tasks=[saved.copy()]
        with patch.object(agent.planner,'plan_todo_list') as plan,patch.object(agent.summarizer,'summarize_task') as summary:
            events=list(agent.run_stream('主题'))
        search.assert_not_called();plan.assert_not_called();summary.assert_not_called()
        reports=[e for e in events if e['type']=='final_report']
        self.assertEqual(len(reports),1);self.assertIn('保留已有成果',reports[0]['report'])
        tasks=next(e['tasks'] for e in events if e['type']=='todo_list')
        self.assertEqual(tasks[0]['summary'],saved['summary']);self.assertEqual(len(self.calls),2)

if __name__=='__main__':unittest.main()
