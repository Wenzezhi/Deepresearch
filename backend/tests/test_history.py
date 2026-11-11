import sys,tempfile,time,unittest
from pathlib import Path
from threading import Event
from fastapi import FastAPI
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from storage import Store
from research_jobs import ResearchJobs, RunInput, router

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.p=self.store.save_profile(dict(name='Test',base_url='https://example.com/v1',model_id='one',api_key='private-key',max_tokens=1000,timeout=30))
    def test_background_survives_client_and_config_change(self):
        gate=Event();captured=[]
        class Agent:
            def __init__(self,config):captured.append(config)
            def run_stream(self,topic):
                yield {'type':'status','message':'started'}
                gate.wait(5)
                yield {'type':'final_report','report':'verified report'}
                yield {'type':'done'}
        jobs=ResearchJobs(self.store,Agent);app=FastAPI();app.include_router(router(self.store,jobs))
        with TestClient(app) as client:
            r=client.post('/research-runs',json={'topic':'test','model_profile_id':self.p['id']}).json()
            self.assertEqual(client.delete('/research-runs/'+r['id']).status_code,409)
            self.store.save_profile({'model_id':'changed'},self.p['id'])
        gate.set()
        for _ in range(100):
            if self.store.run(r['id'])['status']!='running':break
            time.sleep(.02)
        restored=Store(self.store.path)
        self.assertEqual(restored.run(r['id'])['status'],'completed')
        self.assertEqual(captured[0].llm_model_id,'one')
        self.assertEqual(restored.run(r['id'])['profile']['model_id'],'one')
        self.assertNotIn('private-key',str(restored.runs()))
        self.assertTrue(any(e['event']['type']=='final_report' for e in restored.events(r['id'])))
    def test_partial_failure_and_redaction(self):
        class Agent:
            def __init__(self,config):pass
            def run_stream(self,topic):
                yield {'type':'task_status','task_id':1,'status':'failed','detail':'private-key'}
                yield {'type':'final_report','report':'partial report'}
        from profile_api import resolve_config
        jobs=ResearchJobs(self.store,Agent);r=self.store.create_run('partial',self.p,'tavily')
        jobs.execute(r,resolve_config(self.store,self.p['id']))
        self.assertEqual(self.store.run(r['id'])['status'],'partial')
        self.assertNotIn('private-key',str(self.store.events(r['id'])))
    def test_restart_rename_search_delete_and_event_cursor(self):
        r=self.store.create_run('original',self.p,'tavily')
        self.store.append_events(r['id'],[{'type':'status','message':'progress'}])
        self.store.recover_runs()
        self.assertEqual(self.store.run(r['id'])['status'],'interrupted')
        self.assertEqual(len(self.store.events(r['id'],after=1)),1)
        self.store.update_run(r['id'],title='Renamed')
        self.assertEqual(len(self.store.runs('renamed')),1)
        self.assertEqual(self.store.run(r['id'])['topic'],'original')
        self.store.delete_run(r['id']);self.assertEqual(self.store.runs(),[]);self.assertEqual(self.store.events(r['id']),[])
    def test_failure_does_not_become_success(self):
        class Agent:
            def __init__(self,config):raise RuntimeError('private-key failed')
        from profile_api import resolve_config
        r=self.store.create_run('failed',self.p,'tavily')
        ResearchJobs(self.store,Agent).execute(r,resolve_config(self.store,self.p['id']))
        self.assertEqual(self.store.run(r['id'])['status'],'failed')
        self.assertNotIn('private-key',str(self.store.run(r['id'])))
