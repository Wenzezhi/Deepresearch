"""Persistent reading annotations, grounded chat and editable personal notes."""
import json
from uuid import uuid4
from threading import RLock
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel,Field
from openai import OpenAI
from storage import now
from profile_api import resolve_config
from conversation_api import model_details, response_messages, generate_answer

class NoteInput(BaseModel):
 title:str=Field(min_length=1,max_length=200)
 html:str=Field(max_length=8_000_000)
 run_id:str|None=None
class Mark(BaseModel):
 start:int=Field(ge=0)
 end:int=Field(ge=1)
 text:str=Field(max_length=20000)
class Marks(BaseModel):
 marks:list[Mark]=Field(max_length=500)
class Question(BaseModel):
 question:str=Field(min_length=1,max_length=4000)
 quote:str=Field(default='',max_length=20000)
 model_profile_id:str|None=None
 scope:str=Field(max_length=80)
 revision:int=0

def router(store,jobs):
 api=APIRouter(); lock=RLock()
 with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS reading_objects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL)')
 def get(key,kind,default=None):
  with store.connect() as db:r=db.execute('SELECT data FROM reading_objects WHERE id=? AND kind=?',(key,kind)).fetchone()
  return json.loads(r['data']) if r else default
 def put(key,kind,data):
  with store.connect() as db:db.execute('INSERT OR REPLACE INTO reading_objects VALUES(?,?,?)',(key,kind,json.dumps(data,ensure_ascii=False)))
 def run(identifier):
  try:return store.run(identifier)
  except KeyError:raise HTTPException(404,'研究不存在')
 @api.get('/notes')
 def notes():
  with store.connect() as db:items=[json.loads(r['data']) for r in db.execute("SELECT data FROM reading_objects WHERE kind='note'")]
  return sorted([{k:v for k,v in n.items() if k!='html'} for n in items],key=lambda x:x['updated_at'],reverse=True)
 @api.get('/notes/{identifier}')
 def note(identifier:str):
  n=get(identifier,'note')
  if n is None:raise HTTPException(404,'笔记不存在')
  return n
 @api.post('/notes',status_code=201)
 def create(payload:NoteInput):
  if not payload.title.strip():raise HTTPException(422,'请填写笔记标题')
  n=dict(id=uuid4().hex,**payload.model_dump(),created_at=now(),updated_at=now());put(n['id'],'note',n);return n
 @api.put('/notes/{identifier}')
 def update(identifier:str,payload:NoteInput):
  if not payload.title.strip():raise HTTPException(422,'请填写笔记标题')
  n=note(identifier);n.update(**payload.model_dump(),updated_at=now());put(identifier,'note',n);return n
 @api.delete('/notes/{identifier}')
 def delete(identifier:str):
  note(identifier)
  with store.connect() as db:db.execute("DELETE FROM reading_objects WHERE id=? AND kind='note'",(identifier,))
  return {'ok':True}
 @api.get('/reading/{identifier}/{document}')
 def reading(identifier:str,document:str):
  run(identifier);key=identifier+':'+document;data=get(key,'reading')
  if data is None and document=='assistant':
   with store.connect() as db:rows=db.execute("SELECT data FROM reading_objects WHERE kind='reading' AND id LIKE ? ORDER BY rowid",(identifier+':%',)).fetchall()
   messages=[];seen=set()
   for row in rows:
    history=json.loads(row['data']).get('messages',[]);signature=json.dumps(history,sort_keys=True)
    if history and signature not in seen:messages.extend(history);seen.add(signature)
   if messages:data={'marks':[],'messages':messages};put(key,'reading',data)
  if data is None and document.startswith('content-'):
   # Migrate existing highlights for the exact same scope/content hash.
   suffix='-'+document[len('content-'):]
   with store.connect() as db:
    rows=db.execute("SELECT id,data FROM reading_objects WHERE kind='reading' AND id LIKE ? ORDER BY rowid DESC",(identifier+':%',)).fetchall()
   previous=next((json.loads(row['data']) for row in rows if row['id'].endswith(suffix)),None)
   if previous is not None:data=previous;put(key,'reading',data)
  return data or {'marks':[],'messages':[]}
 @api.put('/reading/{identifier}/{document}/marks')
 def marks(identifier:str,document:str,payload:Marks):
  run(identifier)
  if any(m.end<=m.start for m in payload.marks):raise HTTPException(422,'高亮范围无效')
  with lock:
   key=identifier+':'+document;data=get(key,'reading',{'marks':[],'messages':[]});data['marks']=[m.model_dump() for m in payload.marks];put(key,'reading',data)
  return data
 @api.post('/reading/{identifier}/{document}/chat')
 def chat(identifier:str,document:str,payload:Question):
  r=run(identifier)
  if r.get('revision',0)!=payload.revision:raise HTTPException(409,'研究内容已更新，请重新选择文字')
  if not payload.question.strip():raise HTTPException(422,'请输入问题')
  context=''
  if payload.scope in ('report','research'):
   cursor=0
   while True:
    batch=store.events(identifier,cursor)
    for item in batch:
     if item['event'].get('type')=='reset':context=''
     if item['event'].get('type')=='final_report':context=item['event'].get('report','')
    if len(batch)<1000:break
    cursor=batch[-1]['seq']
  else:
   tasks=jobs.snapshot(identifier)
   task=next((t for t in tasks if str(t['id'])==payload.scope),None)
   if task:context=(task.get('summary') or '')+'\n'+(task.get('sources_summary') or '')
  if payload.scope=='research':
   summaries='\n'.join(f"{t['title']}: {t.get('summary') or '暂无总结'}" for t in jobs.snapshot(identifier))
   context=f"研究主题：{r['topic']}\n已有报告：{context}\n子任务：{summaries}"
  if not context:raise HTTPException(409,'当前正文不可用，请等待研究完成')
  key=identifier+':'+document;data=get(key,'reading',{'marks':[],'messages':[]})
  cfg,model=model_details(store,r,payload.model_profile_id)
  messages=response_messages(context,data['messages'],payload.question,payload.quote,model)
  try:
   answer=generate_answer(cfg,model,messages,payload.question,OpenAI)
  except Exception:raise HTTPException(502,'回答生成失败，请检查模型服务后重试')
  if run(identifier).get('revision',0)!=payload.revision:raise HTTPException(409,'研究已更新，本次回答未保存')
  with lock:
   data=get(key,'reading',{'marks':[],'messages':[]});data['messages']+= [{'role':'user','content':payload.question,'quote':payload.quote},{'role':'assistant','content':answer,**model}];put(key,'reading',data)
  return data
 return api
