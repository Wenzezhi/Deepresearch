"""Monotonic elapsed time; concurrent task durations are never summed."""
from time import perf_counter
from threading import Lock

class ResearchTimer:
    def __init__(self, clock=perf_counter):
        self.clock=clock;self.lock=Lock();self.started=clock();self.ended=None
        self.values={};self.active={};self.tasks={}
    def event(self,event):
        with self.lock:
            kind=event.get('type');phase=event.get('phase')
            if kind=='phase':key=phase
            elif kind=='task_timing':key=f"task:{event['task_id']}:{phase}"
            else:return
            now=self.clock()
            if event.get('status')=='started':self.active[key]=now
            elif key in self.active:
                elapsed=max(0,now-self.active.pop(key))
                self.values[key]=float(event.get('elapsed',elapsed)) if kind=='task_timing' else elapsed
    def finish(self):
        with self.lock:
            self.ended=self.clock()
            for key,start in self.active.items():self.values[key]=max(0,self.ended-start)
            self.active.clear()
    def snapshot(self):
        with self.lock:
            end=self.ended if self.ended is not None else self.clock()
            values={**self.values,**{k:max(0,end-v) for k,v in self.active.items()}}
            values['total']=max(0,end-self.started)
            return {'timings':values,'timing_active':{k:True for k in self.active}}
