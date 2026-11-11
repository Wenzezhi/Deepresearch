import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from storage import Store
from research_jobs import ResearchJobs
from reading_api import router
class ReadingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(Path(self.tmp.name)/'db');self.p=self.store.save_profile(dict(name='test',base_url='https://example.com/v1',model_id='test',api_key='secret',max_tokens=1000,timeout=30));self.r=self.store.create_run('topic',self.p,'tavily');self.id=self.r['id'];self.store.append_events(self.id,[{'type':'final_report','report':'# 公开报告\n这是正文'}]);app=FastAPI();app.include_router(router(self.store,ResearchJobs(self.store,None)));self.client=TestClient(app)
 def test_marks_versions_and_notes_persist(self):
  path='/reading/'+self.id+'/v1';marks=[{'start':0,'end':2,'text':'正文'}];self.assertEqual(self.client.put(path+'/marks',json={'marks':marks}).status_code,200);self.assertEqual(self.client.get(path).json()['marks'],marks);self.assertEqual(self.client.get('/reading/'+self.id+'/v2').json()['marks'],[])
  n=self.client.post('/notes',json={'title':'我的笔记','html':'<p>内容</p><img src="data:image/png;base64,example">','run_id':self.id}).json();self.assertEqual(self.client.get('/notes/'+n['id']).json()['html'],n['html']);self.assertNotIn('html',self.client.get('/notes').json()[0]);self.client.put('/notes/'+n['id'],json={'title':'更名','html':'<p>new</p>'});self.assertEqual(self.client.get('/notes').json()[0]['title'],'更名');self.client.delete('/notes/'+n['id']);self.assertEqual(self.client.get('/notes').json(),[])
 @patch('reading_api.OpenAI')
 def test_chat_uses_saved_context_and_profile(self,client):
  response=MagicMock();response.choices[0].message.content='这是解释';client.return_value.__enter__.return_value.chat.completions.create.return_value=response
  path='/reading/'+self.id+'/v1/chat';r=self.client.post(path,json={'quote':'这是正文','question':'什么意思','scope':'report','revision':0});self.assertEqual(r.status_code,200);self.assertEqual(r.json()['messages'][-1]['content'],'这是解释');call=client.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs;self.assertIn('公开报告',str(call['messages']));self.assertEqual(call['model'],'test');self.assertNotIn('secret',str(r.json()));self.store.update_run(self.id,revision=1);self.assertEqual(self.client.post(path,json={'quote':'正文','question':'?','scope':'report','revision':0}).status_code,409)
 @patch('reading_api.OpenAI')
 def test_direct_chat_selects_profile_and_accepts_no_quote(self,client):
  other=self.store.save_profile(dict(name='另一个模型',base_url='https://other.example/v1',model_id='other-model',api_key='other-secret',max_tokens=2000,timeout=40))
  response=MagicMock();response.choices[0].message.content='通俗说明';client.return_value.__enter__.return_value.chat.completions.create.return_value=response
  payload={'question':'总结重点','scope':'research','revision':0,'model_profile_id':other['id']}
  r=self.client.post('/reading/'+self.id+'/assistant/chat',json=payload)
  self.assertEqual(r.status_code,200);self.assertEqual(r.json()['messages'][-1]['model_name'],'另一个模型')
  self.assertEqual(client.call_args.kwargs['base_url'],'https://other.example/v1')
  call=client.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs
  self.assertEqual(call['model'],'other-model');self.assertIn('研究主题',str(call['messages']));self.assertNotIn('other-secret',str(r.json()))
  payload['model_profile_id']='missing';self.assertEqual(self.client.post('/reading/'+self.id+'/assistant/chat',json=payload).status_code,404)
 def test_legacy_highlights_follow_unchanged_content(self):
  mark={'start':0,'end':2,'text':'正文'}
  self.client.put('/reading/'+self.id+'/3-report-abcd/marks',json={'marks':[mark]})
  current=self.client.get('/reading/'+self.id+'/content-report-abcd').json()
  self.assertEqual(current['marks'],[mark]);self.assertEqual(self.client.get('/reading/'+self.id+'/content-report-new').json()['marks'],[])
 @patch('reading_api.OpenAI')
 def test_existing_document_conversation_is_available_in_assistant(self,client):
  response=MagicMock();response.choices[0].message.content='以前的解释';client.return_value.__enter__.return_value.chat.completions.create.return_value=response
  self.client.post('/reading/'+self.id+'/old-document/chat',json={'quote':'正文','question':'以前的问题','scope':'report'})
  data=self.client.get('/reading/'+self.id+'/assistant').json()
  self.assertEqual([m['content'] for m in data['messages']],['以前的问题','以前的解释'])
  self.assertEqual(len(self.client.get('/reading/'+self.id+'/assistant').json()['messages']),2)
if __name__=='__main__':unittest.main()
