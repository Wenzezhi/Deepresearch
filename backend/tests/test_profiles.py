import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from storage import Store
from profile_api import router, resolve_config
from config import Configuration

class ProfilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.sqlite3')
        app=FastAPI();app.include_router(router(self.store));self.client=TestClient(app)
        self.payload=dict(name='Test',base_url='https://example.com/v1',model_id='model-a',api_key='private-test-secret',max_tokens=1024,timeout=45)
    def test_crud_masks_key_and_preserves_blank_edit(self):
        response=self.client.post('/model-profiles',json=self.payload); self.assertEqual(response.status_code,201)
        p=response.json(); self.assertNotIn('private-test-secret',response.text); self.assertTrue(p['has_api_key'])
        self.client.put('/model-profiles/'+p['id'],json={**self.payload,'api_key':'','name':'Changed'})
        self.assertEqual(self.store.profile(p['id'])['api_key'],'private-test-secret')
        self.assertEqual(Store(self.store.path).profiles()[0]['name'],'Changed')
        self.assertNotIn('private-test-secret',self.client.get('/model-profiles').text)
        self.client.delete('/model-profiles/'+p['id']);self.assertEqual(self.store.profiles(),[])
    def test_selected_config_and_snapshot_are_independent(self):
        a=self.store.save_profile(self.payload)
        b=self.store.save_profile({**self.payload,'base_url':'https://other.example/v1','model_id':'model-b'})
        cfg=resolve_config(self.store,a['id'])
        self.assertEqual(resolve_config(self.store,b['id']).llm_model_id,'model-b')
        self.store.save_profile({**self.payload,'model_id':'changed'},a['id'])
        self.assertEqual(cfg.llm_model_id,'model-a');self.assertEqual(cfg.llm_timeout,45)
    def test_env_import_only_once_even_after_delete(self):
        c=Configuration(llm_provider='custom',llm_base_url='https://example.com/v1',llm_api_key='secret')
        self.store.bootstrap(c);p=self.store.profiles()[0];self.store.delete_profile(p['id']);self.store.bootstrap(c)
        self.assertEqual(self.store.profiles(),[])
    def test_validation_and_connection_errors(self):
        self.assertEqual(self.client.post('/model-profiles',json={**self.payload,'base_url':'file:///etc/passwd'}).status_code,422)
        p=self.store.save_profile(self.payload)
        with patch('profile_api.OpenAI',side_effect=RuntimeError('private-test-secret')):
            r=self.client.post('/model-profiles/'+p['id']+'/test')
        self.assertFalse(r.json()['ok']);self.assertNotIn('private-test-secret',r.text)
