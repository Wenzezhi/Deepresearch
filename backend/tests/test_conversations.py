import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from storage import Store
from research_jobs import ResearchJobs
from conversation_api import router

class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db')
        self.profile=self.store.save_profile(dict(name='GLM配置',base_url='https://example.test/v1',model_id='actual-model',api_key='private-key',max_tokens=1000,timeout=20))
        self.run=self.store.create_run('Python研究',self.profile,'tavily');self.run_id=self.run['id']
        self.store.append_events(self.run_id,[{'type':'final_report','report':'研究内容：asyncio 可以并发等待 I/O'}])
        self.jobs=ResearchJobs(self.store,None);app=FastAPI();app.include_router(router(self.store,self.jobs));self.client=TestClient(app)
    def create(self):
        return self.client.post('/research-runs/'+self.run_id+'/conversations').json()['id']
    def send(self,cid,question,**kwargs):
        return self.client.post('/conversations/'+cid+'/messages',json=dict(question=question,model_profile_id=self.profile['id'],**kwargs))
    @patch('conversation_api.OpenAI')
    def test_identity_uses_runtime_configuration_without_guessing(self,client):
        cid=self.create();response=self.send(cid,'你是什么模型？')
        self.assertEqual(response.status_code,200);data=response.json();answer=data['messages'][-1]
        self.assertIn('actual-model',answer['content']);self.assertIn('https://example.test/v1',answer['content']);self.assertNotIn('private-key',str(data));client.assert_not_called()
    @patch('conversation_api.OpenAI')
    def test_free_chat_quotes_and_conversation_isolation(self,client):
        fake=MagicMock();fake.choices[0].message.content='## 回答\n\n**可以自由问答**';client.return_value.__enter__.return_value.chat.completions.create.return_value=fake
        first=self.create();self.send(first,'推荐如何安排学习时间')
        call=client.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(call['messages'][-1]['content'],'推荐如何安排学习时间');self.assertIn('研究之外的自由问答',call['messages'][0]['content']);self.assertIn('asyncio',str(call['messages']))
        second=self.create();self.send(second,'解释这一句',quote='这是参考片段',scope='report')
        call=client.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs
        self.assertNotIn('推荐如何安排学习时间',str(call['messages']));self.assertIn('这是参考片段',call['messages'][-1]['content'])
        self.assertEqual(len(self.client.get('/conversations/'+first).json()['messages']),2)
        history=self.client.get('/research-runs/'+self.run_id+'/conversations').json()
        self.assertEqual(len(history),2);self.assertTrue(all(c['message_count']==2 for c in history));self.assertNotIn('messages',history[0])
    @patch('conversation_api.OpenAI')
    def test_model_switch_keeps_per_message_identity(self,client):
        fake=MagicMock();fake.choices[0].message.content='回答';client.return_value.__enter__.return_value.chat.completions.create.return_value=fake
        cid=self.create();self.send(cid,'第一问')
        other=self.store.save_profile(dict(name='第二个模型',base_url='https://other.test/v1',model_id='second-model',api_key='other-secret',max_tokens=1000,timeout=20))
        response=self.client.post('/conversations/'+cid+'/messages',json={'question':'第二问','model_profile_id':other['id']}).json()
        answers=[m for m in response['messages'] if m['role']=='assistant']
        self.assertEqual([m['model_id'] for m in answers],['actual-model','second-model']);self.assertNotIn('other-secret',str(response))
        self.assertEqual(client.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs['model'],'second-model')
    def test_existing_history_migrates_once(self):
        old={'marks':[],'messages':[{'role':'user','content':'旧问题'},{'role':'assistant','content':'旧回答','model_name':'旧模型'}]}
        with self.store.connect() as db:db.execute('INSERT INTO reading_objects VALUES(?,?,?)',(self.run_id+':assistant','reading',json.dumps(old)))
        url='/research-runs/'+self.run_id+'/conversations'
        first=self.client.get(url).json();again=self.client.get(url).json()
        self.assertEqual(first,again);self.assertEqual(len(first),1);self.assertEqual(self.client.get('/conversations/'+first[0]['id']).json()['messages'],old['messages'])
    @patch('conversation_api.OpenAI')
    def test_failed_request_keeps_question_and_can_continue(self,client):
        client.side_effect=RuntimeError('private-key')
        cid=self.create();response=self.send(cid,'一般问题');self.assertEqual(response.status_code,502);self.assertNotIn('private-key',str(response.json()))
        saved=self.client.get('/conversations/'+cid).json();self.assertEqual(saved['status'],'idle');self.assertEqual(saved['messages'][0]['content'],'一般问题');self.assertIsNotNone(saved['error'])
        self.assertEqual(self.send(cid,'你是什么模型').status_code,200)
    def test_research_update_does_not_block_general_question(self):
        cid=self.create();self.store.update_run(self.run_id,revision=2)
        self.assertEqual(self.send(cid,'你是什么模型',revision=0).status_code,200)

    @patch('conversation_api.OpenAI')
    def test_pending_message_survives_switch_and_duplicate_send_is_blocked(self,client):
        from threading import Event
        from concurrent.futures import ThreadPoolExecutor
        started=Event();release=Event()
        def reply(**kwargs):
            started.set();release.wait(5)
            result=MagicMock();result.choices[0].message.content='保存完成';return result
        client.return_value.__enter__.return_value.chat.completions.create.side_effect=reply
        cid=self.create()
        with ThreadPoolExecutor() as pool:
            future=pool.submit(self.send,cid,'慢速回答')
            try:
                self.assertTrue(started.wait(3))
                saved=self.client.get('/conversations/'+cid).json()
                self.assertEqual(saved['status'],'running');self.assertEqual(saved['messages'][0]['content'],'慢速回答')
                self.assertEqual(self.send(cid,'重复请求').status_code,409)
                other=self.create();self.assertNotEqual(cid,other)
            finally:release.set()
            self.assertEqual(future.result(timeout=5).status_code,200)
        self.assertEqual(self.client.get('/conversations/'+cid).json()['messages'][-1]['content'],'保存完成')
    def test_delete_history_and_legacy_do_not_return(self):
        cid=self.create();self.send(cid,'你是什么模型')
        self.assertEqual(self.client.delete('/conversations/'+cid).status_code,204)
        self.assertEqual(self.client.get('/conversations/'+cid).status_code,404)
        old={'messages':[{'role':'user','content':'旧问题'}]}
        with self.store.connect() as db:db.execute('INSERT INTO reading_objects VALUES(?,?,?)',(self.run_id+':assistant','reading',json.dumps(old)))
        url='/research-runs/'+self.run_id+'/conversations'
        legacy=self.client.get(url).json()[0]['id']
        self.assertEqual(self.client.delete('/conversations/'+legacy).status_code,204)
        self.assertEqual(self.client.get(url).json(),[])

    @patch('conversation_api.generate_answer')
    def test_delete_during_answer_does_not_resurrect(self,answer):
        from threading import Event
        from concurrent.futures import ThreadPoolExecutor
        started=Event();release=Event()
        def reply(*args):started.set();release.wait(5);return '迟到回答'
        answer.side_effect=reply;cid=self.create()
        with ThreadPoolExecutor() as pool:
            future=pool.submit(self.send,cid,'慢速问题')
            try:
                self.assertTrue(started.wait(3))
                self.assertEqual(self.client.delete('/conversations/'+cid).status_code,204)
            finally:release.set()
            self.assertEqual(future.result(timeout=5).status_code,404)
        self.assertEqual(self.client.get('/conversations/'+cid).status_code,404)

    def test_restart_recovers_unfinished_answer(self):
        cid=self.create()
        with self.store.connect() as db:
            data=json.loads(db.execute('SELECT data FROM reading_objects WHERE id=?',(cid,)).fetchone()['data'])
            data.update(status='running');db.execute('UPDATE reading_objects SET data=? WHERE id=?',(json.dumps(data),cid))
        new_app=FastAPI();new_app.include_router(router(self.store,self.jobs))
        saved=TestClient(new_app).get('/conversations/'+cid).json()
        self.assertEqual(saved['status'],'idle');self.assertIn('中断',saved['error'])

class GlobalConversationTests(ConversationTests):
    def test_global_list_includes_existing_runs_and_home_chat(self):
        first=self.create()
        other=self.store.create_run('另一研究',self.profile,'tavily')
        second=self.client.post('/research-runs/'+other['id']+'/conversations').json()['id']
        home=self.client.post('/conversations').json()['id']
        self.assertEqual({c['id'] for c in self.client.get('/conversations').json()},{first,second,home})
        self.assertEqual(self.client.get('/conversations/'+first).status_code,200)
        self.store.update_run(self.run_id,status="completed")
        self.store.delete_run(self.run_id)
        self.assertEqual(self.send(first,'你是什么模型',run_id=None).status_code,200)
        self.assertIn(first,{c['id'] for c in self.client.get('/conversations').json()})

    @patch('conversation_api.OpenAI')
    def test_switch_page_preserves_conversation_and_quote_origin(self,client):
        fake=MagicMock();fake.choices[0].message.content='回答';client.return_value.__enter__.return_value.chat.completions.create.return_value=fake
        other=self.store.create_run('另一研究主题',self.profile,'tavily')
        self.store.append_events(other['id'],[{'type':'final_report','report':'第二份报告的独有内容'}])
        cid=self.client.post('/conversations').json()['id']
        self.send(cid,'解释第一份引用',run_id=self.run_id,quote='asyncio 并发',scope='report')
        response=self.send(cid,'解释第二份引用',run_id=other['id'],quote='第二份报告',scope='report').json()
        users=[m for m in response['messages'] if m['role']=='user']
        self.assertEqual([m['quote_source']['run_id'] for m in users],[self.run_id,other['id']])
        sent=client.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs['messages']
        self.assertIn('第二份报告的独有内容',sent[1]['content'])
        self.assertIn(self.run_id,str(sent[2]))
        self.send(cid,'普通聊天',run_id=None)
        sent=client.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs['messages']
        self.assertNotIn('第二份报告的独有内容',str(sent))
        self.assertEqual(sent[-1]['content'],'普通聊天')

    @patch('conversation_api.OpenAI')
    @patch('conversation_api.beijing_now')
    def test_current_time_uses_request_clock_without_model_call(self,clock,client):
        from datetime import datetime,timezone,timedelta
        clock.return_value=datetime(2026,11,1,13,20,30,tzinfo=timezone(timedelta(hours=8)))
        cid=self.client.post('/conversations').json()['id']
        response=self.send(cid,'现在是北京时间几点？',run_id=None)
        self.assertEqual(response.status_code,200)
        self.assertIn('2026-11-01 13:20:30',response.json()['messages'][-1]['content'])
        clock.return_value=datetime(2026,11,1,14,21,31,tzinfo=timezone(timedelta(hours=8)))
        response=self.send(cid,'北京时间几点',run_id=None)
        self.assertIn('14:21:31',response.json()['messages'][-1]['content']);client.assert_not_called()

    @patch('conversation_api.OpenAI')
    @patch('conversation_api.beijing_now')
    def test_free_chat_receives_fresh_time_and_no_required_research(self,clock,client):
        from datetime import datetime,timezone,timedelta
        clock.return_value=datetime(2026,11,1,16,30,0,tzinfo=timezone(timedelta(hours=8)))
        fake=MagicMock();fake.choices[0].message.content='可以';client.return_value.__enter__.return_value.chat.completions.create.return_value=fake
        cid=self.client.post('/conversations').json()['id'];self.send(cid,'帮我安排今晚的学习',run_id=None)
        sent=client.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs['messages']
        self.assertIn('2026-11-01 16:30:00',sent[0]['content']);self.assertIn('UTC+8',sent[0]['content'])
        self.assertFalse(any('可选研究背景' in m['content'] for m in sent))
        self.assertEqual(sent[-1]['content'],'帮我安排今晚的学习')

    def test_global_legacy_migration_and_delete(self):
        old={'messages':[{'role':'user','content':'旧问题'}]}
        with self.store.connect() as db:db.execute('INSERT INTO reading_objects VALUES(?,?,?)',(self.run_id+':assistant','reading',json.dumps(old)))
        first=self.client.get('/conversations').json()
        self.assertEqual(len(first),1)
        self.client.delete('/conversations/'+first[0]['id'])
        self.assertEqual(self.client.get('/conversations').json(),[])

if __name__=='__main__':unittest.main()

