"""Durable event journal and background execution independent of browser lifetime."""
import json
import time
from pathlib import Path
from threading import Thread, Event, RLock
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from config import SearchAPI
from storage import now
from timing import ResearchTimer
from profile_api import resolve_config
from services.search import _safe_error


class RunInput(BaseModel):
    topic: str = Field(min_length=1, max_length=2000)
    model_profile_id: str
    search_api: SearchAPI | None = None
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    @field_validator('topic')
    @classmethod
    def clean(cls,v):
        if not v.strip(): raise ValueError('请输入研究主题')
        return v.strip()

class RenameInput(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    @field_validator('title')
    @classmethod
    def clean(cls,v):
        if not v.strip(): raise ValueError('标题不能为空')
        return v.strip()


class ResearchJobs:
    def __init__(self, store, agent_factory, document_library=None):
        self.store=store; self.agent_factory=agent_factory; self.document_library=document_library
        self.lock=RLock(); self.tokens={}; self.pending_retries={}

    def start(self, payload):
        try: raw_profile=self.store.profile(payload.model_profile_id); profile=self.store.public(raw_profile)
        except KeyError: raise HTTPException(404,'模型配置不存在')
        from config import Configuration
        config=Configuration.from_env(dict(llm_provider='custom',llm_base_url=raw_profile['base_url'],llm_model_id=raw_profile['model_id'],llm_api_key=raw_profile['api_key'] or 'not-required',llm_max_tokens=raw_profile['max_tokens'],llm_timeout=raw_profile['timeout'],search_api=payload.search_api))
        # Snapshot contains identifying settings only, never a credential.
        profile.pop('has_api_key',None)
        identifier=uuid4().hex
        config.notes_workspace=str(Path(__file__).resolve().parents[1]/'notes'/identifier)
        document_ids=list(dict.fromkeys(payload.document_ids or []))
        if len(document_ids) > 20:
            raise HTTPException(422, "一次研究最多选择 20 篇本地文献")
        if document_ids and self.document_library is None:
            raise HTTPException(400, "本地文献资料库尚未启用")
        for document_id in document_ids:
            try:
                self.document_library.get_document(document_id)
            except KeyError as exc:
                raise HTTPException(422, f"所选本地文献不存在：{document_id}") from exc
        record=self.store.create_run(payload.topic,profile,config.search_api.value,identifier,document_ids=document_ids)
        token=Event()
        with self.lock: self.tokens[identifier]=token
        thread=Thread(target=self.execute,args=(record,config,None,token),daemon=True)
        thread.start()
        return record

    def snapshot(self, identifier):
        tasks={}; cursor=0
        while True:
            batch=self.store.events(identifier,cursor)
            for item in batch:
                e=item['event']; kind=e.get('type')
                if kind=='reset': tasks={}
                if kind in ('todo_list','tasks_updated'): tasks={t['id']:dict(t) for t in e['tasks']}
                if kind=='task_status' and e.get('task_id') in tasks:
                    tasks[e['task_id']].update({k:v for k,v in e.items() if k not in ('type','task_id')})
            if len(batch)<1000: break
            cursor=batch[-1]['seq']
        run_status=self.store.run(identifier)['status']
        if run_status in ('paused','interrupted'):
            for task in tasks.values():
                if task.get('status') in ('pending','in_progress'):task['status']=run_status
        return list(tasks.values())

    def pause(self, identifier):
        with self.lock:
            r=self.store.run(identifier)
            if r['status']!='running': return r
            token=self.tokens.get(identifier)
            if token: token.set()
            queued=self.pending_retries.pop(identifier,[])
            if queued:self.store.append_events(identifier,[{'type':'task_retry_queue_cleared','task_ids':queued}])
            self.store.append_events(identifier,[{'type':'task_status','task_id':t['id'],'status':'paused'} for t in self.snapshot(identifier) if t.get('status') in ('pending','in_progress')]+[{'type':'status','message':'研究已暂停，已完成任务保留。'}])
            return self.store.update_run(identifier,status='paused',timing_active={},updated_at=now())

    def retry(self, identifier, task_id):
        with self.lock:
            r=self.store.run(identifier)
            task=next((t for t in self.snapshot(identifier) if t['id']==task_id),None)
            if task is None:raise HTTPException(404,'任务不存在')
            if task.get('status') not in ('failed','paused','skipped','interrupted'):raise HTTPException(409,'只能重试失败或暂停的任务')
            if r['status']=='running':
                queue=self.pending_retries.setdefault(identifier,[])
                if task_id not in queue:
                    queue.append(task_id)
                    self.store.append_events(identifier,[{'type':'task_retry_queued','task_id':task_id}])
                return r
            return self.restart(identifier,retry_id=task_id)

    def restart(self, identifier, tasks=None, topic=None, retry_id=None):
        with self.lock:
            r=self.store.run(identifier)
            if r['status']=='running': raise HTTPException(409,'请先暂停研究')
            if self.document_library is not None:
                for document_id in (r.get('document_ids') or []):
                    try:
                        self.document_library.get_document(document_id)
                    except KeyError as exc:
                        raise HTTPException(409,'本次研究引用的本地文献已被删除，请重新导入文献并创建新的研究任务。') from exc
            config=resolve_config(self.store,(r.get('profile') or {}).get('id'),r.get('search_api'))
            old={t['id']:t for t in self.snapshot(identifier)}
            changed_ids=[]
            if topic is not None:
                seed=None
            elif retry_id is not None:
                changed_ids=retry_id if isinstance(retry_id,list) else [retry_id]
                for task_id in changed_ids:
                    target=old.get(task_id)
                    if target is None: raise HTTPException(404,'任务不存在')
                    if target.get('status') not in ('failed','paused','interrupted','skipped','pending','in_progress'): raise HTTPException(409,'只能重试失败或暂停的任务')
                seed=[dict(t) for t in old.values()]
            elif tasks is None:
                seed=[dict(t) for t in old.values()] or None
                changed_ids=[t['id'] for t in seed or [] if t.get('status')!='completed']
            else:
                seed=[]; next_id=max(old.keys(),default=0)+1; seen=set()
                for t in tasks:
                    task_id=t.get('id')
                    if task_id is not None and (task_id not in old or task_id in seen): raise HTTPException(422,'任务标识无效或重复')
                    if task_id is None: task_id=next_id;next_id+=1
                    seen.add(task_id); previous=old.get(task_id,{})
                    if t['intent']!=previous.get('intent') or t['title']!=previous.get('title'):changed_ids.append(task_id)
                    seed.append({**previous,**t,'id':task_id})
            for t in seed or []:
                if t['id'] in changed_ids:
                    t.update(status='pending',query='',summary='',sources_summary='',note_id=None,note_path=None,error=None,notices=[])
                elif t.get('status') in ('pending','in_progress'):t['status']='paused'
            revision=r.get('revision',0)+1
            config.notes_workspace=str(Path(__file__).resolve().parents[1]/'notes'/identifier/f'revision-{revision}')
            if topic is not None:
                with self.store.connect() as db: db.execute('DELETE FROM events WHERE run_id=?',(identifier,))
            if seed is None:
                self.store.append_events(identifier,[{'type':'reset'}])
            else:
                self.store.append_events(identifier,[{'type':'tasks_updated','tasks':seed,'changed_ids':changed_ids,'revision':revision}])
            r=self.store.update_run(identifier,status='running',error=None,revision=revision,topic=topic or r['topic'],title=topic or r['title'],updated_at=now(),ended_at=None)
            token=Event();self.tokens[identifier]=token
            Thread(target=self.execute,args=(r,config,seed,token),daemon=True).start()
            return r

    def execute(self, record, config, seed=None, token=None):
        identifier=record['id']; partial=any(t.get('status') not in ('pending','completed') for t in seed or []); report=False; error=None
        with self.lock:
            if token is None:
                token=Event(); self.tokens[identifier]=token
                if self.store.run(identifier)['status']!='running': token.set()
        def current(): return self.tokens.get(identifier) is token and not token.is_set()

        timer=ResearchTimer();stop_heartbeat=Event()
        def checkpoint():
            with self.lock:
                if current(): self.store.update_run(identifier,updated_at=now(),**timer.snapshot())
        def heartbeat():
            while not stop_heartbeat.wait(1): checkpoint()
        checkpoint()
        heartbeat_thread=Thread(target=heartbeat,daemon=True);heartbeat_thread.start()
        pending=[]; last_flush=time.monotonic()
        def flush():
            nonlocal pending,last_flush
            with self.lock:
                if current(): self.store.append_events(identifier,pending)
                pending=[];last_flush=time.monotonic()
            checkpoint()
        def append(event):
            # Redact custom-profile keys as well as environment secrets.
            text=json.dumps(event,ensure_ascii=False)
            if config.llm_api_key and config.llm_api_key!='not-required': text=text.replace(config.llm_api_key,'[REDACTED]')
            event=json.loads(text)
            if event.get('type')=='task_summary_chunk' and pending and pending[-1].get('type')=='task_summary_chunk' and pending[-1].get('task_id')==event.get('task_id'):
                pending[-1]['content']+=event.get('content','')
            else: pending.append(event)
            if event.get('type')!='task_summary_chunk' or time.monotonic()-last_flush>=.2: flush()
        try:
            agent=self.agent_factory(config=config);agent.cancel_event=token
            agent.document_library=self.document_library
            agent.local_document_ids=list(record.get('document_ids') or [])
            # Completed results are included directly in the report. Old note files belong to a previous workspace.
            agent.resume_tasks=[{**t,'note_id':None,'note_path':None} if t.get('status')!='pending' else dict(t) for t in seed] if seed is not None else None
            if hasattr(agent,'llm'): agent.llm.cancel_event=token
            for event in agent.run_stream(record['topic']):
                if not current(): break
                if event.get('type')=='done': continue
                if event.get('type')=='todo_list' and seed is not None:
                    preserved={t['id']:t for t in seed if t.get('status')!='pending'}
                    event={**event,'tasks':[preserved.get(t['id'],t) for t in event['tasks']]}
                if event.get('type')=='final_report':event={**event,'revision':record.get('revision',0)}
                timer.event(event)
                append(event)
                if event.get('type')=='final_report': report=bool(event.get('report','').strip())
                if event.get('type')=='error': error=event.get('detail','研究失败')
                if event.get('type')=='task_status' and event.get('status') in ('failed','skipped'): partial=True
            if not report and not error:
                error='研究结束但没有生成报告';append({'type':'error','detail':error})
        except Exception as exc:
            error=_safe_error(exc)
            if config.llm_api_key: error=error.replace(config.llm_api_key,'[REDACTED]')
            append({'type':'error','detail':error})
        finally:
            if error and config.llm_api_key: error=error.replace(config.llm_api_key,'[REDACTED]')
            stop_heartbeat.set();heartbeat_thread.join()
            timer.finish()
            append({'type':'done'});flush()
            with self.lock:
                if current():
                    self.store.update_run(identifier,status='failed' if error else 'partial' if partial else 'completed',error=error,ended_at=now(),updated_at=now())
                    queued=self.pending_retries.pop(identifier,[])
                    if queued:self.restart(identifier,retry_id=queued)


class TaskEdit(BaseModel):
    id: int | None = None
    title: str = Field(min_length=1,max_length=160)
    intent: str = Field(min_length=1,max_length=4000)
    @field_validator('title','intent')
    @classmethod
    def nonempty(cls,v):
        if not v.strip(): raise ValueError('任务标题与研究要求不能为空')
        return v.strip()
class TasksEdit(BaseModel):
    tasks: list[TaskEdit] = Field(min_length=1,max_length=20)
class TopicEdit(BaseModel):
    topic: str = Field(min_length=1,max_length=2000)
    @field_validator('topic')
    @classmethod
    def nonempty(cls,v):
        if not v.strip(): raise ValueError('主题不能为空')
        return v.strip()

def router(store,jobs):
    api=APIRouter(prefix='/research-runs')
    def find(identifier):
        try:return store.run(identifier)
        except KeyError:raise HTTPException(404,'研究记录不存在')
    @api.post('',status_code=202)
    def start(payload:RunInput):return jobs.start(payload)
    @api.get('')
    def list_runs(q:str=''):return store.runs(q)
    @api.get('/{identifier}')
    def detail(identifier:str,after:int=Query(0,ge=0)):
        # Read metadata first. A terminal status then guarantees final events have been committed.
        record=find(identifier); events=store.events(identifier,after)
        return dict(record=record,events=events,next_cursor=events[-1]['seq'] if events else after,has_more=len(events)==1000)
    @api.post('/{identifier}/pause')
    def pause(identifier:str):find(identifier);return jobs.pause(identifier)
    @api.post('/{identifier}/resume')
    def resume(identifier:str):find(identifier);return jobs.restart(identifier)
    @api.put('/{identifier}/tasks')
    def tasks(identifier:str,payload:TasksEdit):find(identifier);return jobs.restart(identifier,tasks=[t.model_dump() for t in payload.tasks])
    @api.post('/{identifier}/tasks/{task_id}/retry')
    def retry(identifier:str,task_id:int):find(identifier);return jobs.retry(identifier,task_id)
    @api.put('/{identifier}/topic')
    def topic(identifier:str,payload:TopicEdit):find(identifier);return jobs.restart(identifier,topic=payload.topic)
    @api.patch('/{identifier}')
    def rename(identifier:str,payload:RenameInput):
        find(identifier);return store.update_run(identifier,title=payload.title)
    @api.delete('/{identifier}')
    def delete(identifier:str):
        find(identifier)
        try:store.delete_run(identifier)
        except ValueError as exc:raise HTTPException(409,str(exc))
        return {'ok':True}
    return api
