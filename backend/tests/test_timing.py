import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from timing import ResearchTimer

class TimingTests(unittest.TestCase):
    def setUp(self):self.t=0;self.timer=ResearchTimer(lambda:self.t)
    def phase(self,phase,status):self.timer.event(dict(type='phase',phase=phase,status=status))
    def task(self,i,status):self.timer.event(dict(type='task_timing',phase='search',task_id=i,status=status))
    def test_concurrent_time_is_not_sum(self):
        self.phase('planning','started');self.t=2;self.phase('planning','finished')
        self.phase('execution','started');self.task(1,'started');self.task(2,'started')
        self.t=6;self.task(1,'finished');self.t=8;self.task(2,'finished');self.phase('execution','finished')
        self.phase('report','started');self.t=10;self.phase('report','finished');self.timer.finish()
        result=self.timer.snapshot()['timings']
        self.assertEqual(result['execution'],6);self.assertEqual(result['total'],10)
        self.assertEqual(result['task:1:search']+result['task:2:search'],10)
        self.t=100;self.assertEqual(self.timer.snapshot()['timings']['total'],10)
    def test_failure_freezes_active_stages(self):
        self.phase('planning','started');self.t=3;self.timer.finish();self.t=40
        result=self.timer.snapshot();self.assertEqual(result['timings']['planning'],3);self.assertEqual(result['timing_active'],{})
        self.assertNotIn('report',result['timings'])
    def test_running_snapshot(self):
        self.phase('report','started');self.t=2
        result=self.timer.snapshot();self.assertEqual(result['timings']['report'],2);self.assertTrue(result['timing_active']['report'])
