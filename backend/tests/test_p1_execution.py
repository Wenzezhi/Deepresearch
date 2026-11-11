import unittest,tempfile,time,sys
from pathlib import Path
from threading import Event
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from storage import Store
from research_jobs import ResearchJobs
from profile_api import resolve_config
class P1ExecutionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=Store(Path(self.temp.name)/'p1.db');self.p=self.store.save_profile(dict(name='test',base_url='https://example.com/v1',model_id='test',api_key='',max_tokens=1000,timeout=30));self.r=self.store.create_run('topic',self.p,'tavily');self.id=self.r['id'];self.jobs=ResearchJobs(self.store,lambda **kw:None)
  self.store.append_events(self.id,[{'type':'todo_list','tasks':[{'id':1,'title':'A','intent':'a','query':'q1','status':'completed','summary':'keep'},{'id':2,'title':'B','intent':'b','query':'q2','status':'failed'}]}]);self.store.update_run(self.id,status='completed')
 @patch('research_jobs.Thread')
 def test_edit_preserves_success_infers_query_and_reorders(self,thread):
  self.jobs.restart(self.id,tasks=[{'id':2,'title':'B','intent':'new natural language'},{'id':1,'title':'A','intent':'a'},{'id':None,'title':'C','intent':'c'}]);seed=thread.call_args.kwargs['args'][2]
  self.assertEqual([t['id'] for t in seed],[2,1,3]);self.assertEqual(seed[0]['query'],'');self.assertEqual(seed[1]['summary'],'keep');self.assertEqual(seed[1]['status'],'completed');self.assertEqual(self.store.run(self.id)['revision'],1)
 @patch('research_jobs.Thread')
 def test_topic_overwrites_events(self,thread):
  self.jobs.restart(self.id,topic='new topic');self.assertIsNone(thread.call_args.kwargs['args'][2]);self.assertEqual(self.store.run(self.id)['topic'],'new topic');self.assertEqual([e['event']['type'] for e in self.store.events(self.id)],['reset'])
 def test_pause_rejects_late_output(self):
  gate=Event();started=Event();finished=Event()
  class Agent:
   def __init__(self,**kw):pass
   def run_stream(self,topic):
    started.set();gate.wait(5);yield {'type':'final_report','report':'late'};finished.set()
  self.store.update_run(self.id,status='running');jobs=ResearchJobs(self.store,Agent)
  from threading import Thread
  worker=Thread(target=jobs.execute,args=(self.store.run(self.id),resolve_config(self.store,self.p['id'])));worker.start();started.wait(3);jobs.pause(self.id);gate.set();worker.join(5)
  self.assertEqual(self.store.run(self.id)['status'],'paused');self.assertFalse(any(e['event'].get('report')=='late' for e in self.store.events(self.id)))
 @patch('research_jobs.Thread')
 def test_incremental_edit_keeps_report_and_other_failed_tasks(self,thread):
  self.store.append_events(self.id,[{'type':'final_report','report':'old report'}])
  self.jobs.restart(self.id,tasks=[{'id':1,'title':'A','intent':'changed a'},{'id':2,'title':'B','intent':'b'}])
  seed=thread.call_args.kwargs['args'][2]
  self.assertEqual(seed[0]['status'],'pending');self.assertEqual(seed[1]['status'],'failed')
  events=[x['event'] for x in self.store.events(self.id)]
  self.assertNotIn('reset',[e['type'] for e in events]);self.assertEqual(events[-1]['changed_ids'],[1]);self.assertTrue(any(e.get('report')=='old report' for e in events))
 @patch('research_jobs.Thread')
 def test_single_retry_keeps_all_other_results(self,thread):
  self.store.append_events(self.id,[{'type':'task_status','task_id':1,'status':'paused','summary':'keep'}])
  self.jobs.restart(self.id,retry_id=2)
  seed=thread.call_args.kwargs['args'][2]
  self.assertEqual(seed[0]['status'],'paused');self.assertEqual(seed[0]['summary'],'keep');self.assertEqual(seed[1]['status'],'pending')
  self.assertEqual(self.store.events(self.id)[-1]['event']['changed_ids'],[2])
 @patch('research_jobs.Thread')
 def test_reorder_has_no_execution_targets(self,thread):
  self.jobs.restart(self.id,tasks=[{'id':2,'title':'B','intent':'b'},{'id':1,'title':'A','intent':'a'}])
  seed=thread.call_args.kwargs['args'][2]
  self.assertEqual([t['id'] for t in seed],[2,1]);self.assertEqual([t['status'] for t in seed],['failed','completed'])
  self.assertEqual(self.store.events(self.id)[-1]['event']['changed_ids'],[])
 def test_retry_during_other_work_is_queued_then_started_once(self):
  from unittest.mock import Mock
  self.store.update_run(self.id,status='running')
  self.jobs.retry(self.id,2);self.jobs.retry(self.id,2)
  self.assertEqual(self.jobs.pending_retries[self.id],[2])
  self.assertEqual(sum(e['event']['type']=='task_retry_queued' for e in self.store.events(self.id)),1)
  self.jobs.agent_factory=Mock(return_value=Mock(run_stream=Mock(return_value=iter([{'type':'final_report','report':'done'}]))))
  with patch.object(self.jobs,'restart') as restart:
   self.jobs.execute(self.store.run(self.id),resolve_config(self.store,self.p['id']))
   restart.assert_called_once_with(self.id,retry_id=[2])
 def test_pause_cancels_queued_retry(self):
  self.store.update_run(self.id,status='running');self.jobs.retry(self.id,2);self.jobs.pause(self.id)
  self.assertNotIn(self.id,self.jobs.pending_retries)
  self.assertTrue(any(e['event']['type']=='task_retry_queue_cleared' for e in self.store.events(self.id)))
 @patch('research_jobs.Thread')
 def test_legacy_paused_task_can_retry(self,thread):
  self.store.append_events(self.id,[{'type':'task_status','task_id':2,'status':'in_progress'}]);self.store.update_run(self.id,status='paused')
  self.jobs.retry(self.id,2);seed=thread.call_args.kwargs['args'][2]
  self.assertEqual(seed[1]['status'],'pending');self.assertEqual(seed[0]['summary'],'keep')
if __name__=='__main__':unittest.main()

class QueryGenerationTests(unittest.TestCase):
 @patch('agent.dispatch_search')
 def test_natural_requirements_generate_query_and_reuse_success(self,search):
  from unittest.mock import Mock
  from test_search_resilience import WorkflowTests,result
  fixture=WorkflowTests();agent=fixture.make_agent([]);agent.llm=Mock();agent.llm.invoke.return_value='low cost multimodal gpu memory';agent.resume_tasks=[{'id':1,'title':'成功任务','intent':'旧要求','query':'old','status':'completed','summary':'保留结果'},{'id':2,'title':'低成本训练','intent':'重点分析小团队显存和预算','query':'','status':'pending'}];search.return_value=(result(),[],None,'tavily')
  events=list(agent.run_stream('多模态研究'));search.assert_called_once();self.assertEqual(search.call_args.args[0],'low cost multimodal gpu memory');self.assertIn('重点分析小团队显存和预算',str(agent.llm.invoke.call_args));state=agent.reporting.generate_report.call_args.args[0];self.assertEqual(state.todo_items[0].summary,'保留结果');self.assertTrue(any(e['type']=='final_report' for e in events))

class SingleExecutionTests(unittest.TestCase):
 @patch('agent.dispatch_search')
 def test_only_pending_target_executes(self,search):
  from unittest.mock import Mock
  from test_search_resilience import WorkflowTests,result
  fixture=WorkflowTests();agent=fixture.make_agent([]);agent.llm=Mock();agent.llm.invoke.return_value='generated query'
  agent.resume_tasks=[{'id':1,'title':'成功','intent':'旧要求','query':'old','status':'completed','summary':'unchanged'},{'id':2,'title':'重试','intent':'新要求','query':'','status':'pending'},{'id':3,'title':'其他失败','intent':'旧要求','query':'','status':'failed'},{'id':4,'title':'其他暂停','intent':'旧要求','query':'','status':'paused'}]
  search.return_value=(result(),[],None,'tavily');events=list(agent.run_stream('topic'))
  self.assertEqual(search.call_count,1);self.assertEqual(agent.llm.invoke.call_count,1)
  self.assertEqual([e['task_id'] for e in events if e['type']=='task_status' and e['status']=='in_progress'],[2])
  tasks=agent.reporting.generate_report.call_args.args[0].todo_items
  self.assertEqual(tasks[0].summary,'unchanged');self.assertEqual(tasks[2].status,'failed');self.assertEqual(tasks[3].status,'paused')

 @patch('agent.dispatch_search')
 def test_query_failure_is_retryable_without_touching_success(self,search):
  from unittest.mock import Mock
  from test_search_resilience import WorkflowTests
  agent=WorkflowTests().make_agent([]);agent.llm=Mock();agent.llm.invoke.side_effect=RuntimeError('timeout')
  agent.resume_tasks=[{'id':1,'title':'成功','intent':'a','query':'q','status':'completed','summary':'keep'},{'id':2,'title':'更新','intent':'b','query':'','status':'pending'}]
  events=list(agent.run_stream('topic'));search.assert_not_called()
  self.assertTrue(any(e['type']=='task_status' and e['task_id']==2 and e['status']=='failed' for e in events))
  self.assertEqual(agent.reporting.generate_report.call_args.args[0].todo_items[0].summary,'keep')
