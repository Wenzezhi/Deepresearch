<template>
<aside class="chat-panel" :class="{embedded}" @keydown.esc="historyOpen=false">
  <header class="chat-header"><h3>对话助手</h3><div class="header-actions">
    <button v-if="!embedded" type="button" aria-label="历史对话" title="历史对话" :aria-expanded="historyOpen" :class="{selected:historyOpen}" @click="toggleHistory"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
    <button type="button" aria-label="新建对话" title="新建对话" @click="newConversation">{{ embedded ? '＋ 新建对话' : '＋' }}</button>
    <button v-if="!embedded" type="button" aria-label="关闭聊天" title="关闭聊天" @click="$emit('close')">×</button>
  </div></header>
  <div v-if="activeTitle && messages.length" class="conversation-title" :title="activeTitle"><svg class="conversation-folder" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="M3 5h6l2 2h10v13H3z"/><path d="M3 10h18"/></svg><span>{{ activeTitle }}</span></div>
  <div v-if="historyOpen && !embedded" class="history-backdrop" @click="historyOpen=false"></div>
  <Teleport :to="embedded ? '#home-conversation-history' : 'body'" :disabled="!embedded" defer>
  <section v-if="embedded || historyOpen" class="chat-history" :class="{'embedded-history':embedded}" :role="embedded ? 'region' : 'dialog'" aria-label="历史对话列表">
    <header><h4>{{ embedded ? '对话历史' : '全部对话' }}</h4><span v-if="embedded">{{ history.length }} 项</span><button v-else type="button" aria-label="关闭历史列表" @click="historyOpen=false">×</button></header>
    <small v-if="!embedded">所有页面共用 · 自动保存</small>
    <input v-model="historyQuery" type="search" aria-label="搜索对话" :placeholder="embedded ? '搜索对话历史' : '搜索全部对话…'"/>
    <div class="conversation-list"><p v-if="!filteredHistory.length" class="history-empty">{{ historyQuery?'没有匹配的对话':'暂无历史对话' }}</p>
      <template v-for="(item,index) in filteredHistory" :key="item.id">
        <p v-if="index===0 || dateLabel(item.updated_at)!==dateLabel(filteredHistory[index-1].updated_at)" class="history-date">{{ dateLabel(item.updated_at) }}</p>
        <div class="history-item"><button type="button" :class="['conversation-row',{active:item.id===activeId}]" @click="openConversation(item.id)"><strong>{{ item.title }}</strong><time>{{ timeLabel(item.updated_at) }}</time><span>{{ item.preview || '尚无消息' }}</span><small>{{ item.message_count }} 条消息{{ item.status==='running'?' · 回答中':'' }}</small></button><button type="button" class="delete-conversation" :aria-label="'删除对话：'+item.title" title="删除对话" @click="askDelete(item)">×</button></div>
      </template>
    </div>
    <p v-if="historyError" class="error" role="alert">{{ historyError }}</p><p v-if="embedded" class="history-local-hint">对话记录保存在本机</p>
  </section>
  </Teleport>
  <div v-if="deleteTarget" class="delete-overlay" @keydown.esc.stop="!deleting && (deleteTarget=null)"><section role="alertdialog" aria-modal="true" aria-labelledby="delete-chat-title" class="delete-dialog" @keydown.tab.prevent="focusDeleteAction">
    <h4 id="delete-chat-title">确定删除这条对话？</h4><p>“{{ deleteTarget.title }}”及其消息将被删除，无法恢复。</p><p v-if="deleteError" class="error" role="alert">{{ deleteError }}</p>
    <div><button ref="cancelDeleteButton" type="button" class="cancel-delete" :disabled="deleting" @click="deleteTarget=null">取消</button><button ref="confirmDeleteButton" type="button" class="confirm-delete" :disabled="deleting" @click="deleteConversation">{{ deleting?'正在删除…':'确认删除' }}</button></div>
  </section></div>
  <div ref="messageList" class="chat-messages" aria-live="polite">
    <div v-if="!messages.length && !busy && !initializing" class="chat-welcome"><div class="assistant-logo" aria-hidden="true">⬡</div><h2>{{ embedded ? '对话助手' : '研究小助手' }}</h2><p>想聊点什么？</p></div>
    <p v-if="initializing">正在载入对话…</p>
    <div v-for="(m,i) in messages" :key="i" :class="['message',m.role]"><small v-if="m.quote">引用<span v-if="m.quote_source?.topic"> · {{ m.quote_source.topic }}</span>：{{ m.quote }}</small><ChatMarkdown v-if="m.role==='assistant'" :content="m.content"/><p v-else>{{ m.content }}</p><small v-if="m.role==='assistant' && m.model_name" class="model-caption" :title="[m.model_id,m.api_base_url].filter(Boolean).join(' · ')">{{ m.model_name }}<span v-if="m.model_id && m.model_id!==m.model_name"> · {{ m.model_id }}</span></small></div>
    <p v-if="busy" role="status">正在回答…</p>
  </div>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <form @submit.prevent="send">
    <blockquote v-if="quote" class="quote-preview"><header><small>引用 · {{ context.scope==='report'?'最终报告':'任务总结' }}</small><button type="button" aria-label="取消引用" @click="quote=''">×</button></header><p>{{ quote }}</p></blockquote>
    <textarea v-model="question" placeholder="输入问题…" aria-label="聊天问题" @keydown="composerKeydown" @compositionstart="composing=true" @compositionend="composing=false" rows="3" maxlength="4000" :disabled="busy || initializing"/>
    <div class="composer-actions"><label class="chat-model-label"><span v-if="embedded">对话模型</span><select :value="modelId" @change="chooseModel" aria-label="对话模型" :disabled="busy"><option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option><option v-if="!profiles.length" value="">请先配置模型</option></select></label><button class="send" :disabled="busy || initializing || !question.trim() || !modelId">发送 ↑</button></div>
    <small class="model-hint">与首页模型配置同步 · Enter 发送，Shift+Enter 换行</small>
  </form>
</aside>
</template>
<script setup lang="ts">
import ChatMarkdown from './ChatMarkdown.vue';
import {ref,watch,nextTick,onBeforeUnmount,onMounted,computed} from 'vue';import {api,type ModelProfile} from '../services/api';
export interface ChatContext{runId:string;document:string;scope:string;revision:number;quote:string}
interface Message{quote_source?:{run_id?:string;topic?:string;scope?:string;revision?:number}|null;role:string;content:string;quote?:string;model_name?:string;model_id?:string;model_profile_id?:string;api_base_url?:string}
interface Conversation{id:string;run_id:string;title:string;messages:Message[];status:string;error?:string;updated_at:string}
interface HistoryItem{id:string;title:string;preview:string;status:string;message_count:number;updated_at:string}
const props=defineProps<{context:ChatContext;profiles:ModelProfile[];defaultModelId?:string;embedded?:boolean}>();const emit=defineEmits<{close:[];modelChoice:[id:string]}>();
const messages=ref<Message[]>([]);const question=ref('');const quote=ref('');const modelId=ref('');const sending=ref(false);const remoteBusy=ref(false);const busy=computed(()=>sending.value||remoteBusy.value);const error=ref('');const messageList=ref<HTMLElement|null>(null);
const activeId=ref('');const activeTitle=ref('');const initializing=ref(false);const historyOpen=ref(false);const historyQuery=ref('');const history=ref<HistoryItem[]>([]);const historyError=ref('');let epoch=0;let timer:ReturnType<typeof setInterval>|undefined;let polling=false;
const deleteTarget=ref<HistoryItem|null>(null);const deleting=ref(false);const deleteError=ref('');const cancelDeleteButton=ref<HTMLButtonElement|null>(null);const confirmDeleteButton=ref<HTMLButtonElement|null>(null);
function askDelete(item:HistoryItem){deleteTarget.value=item;deleteError.value='';void nextTick(()=>cancelDeleteButton.value?.focus());}
function focusDeleteAction(){(document.activeElement===cancelDeleteButton.value?confirmDeleteButton.value:cancelDeleteButton.value)?.focus();}
async function deleteConversation(){const target=deleteTarget.value;if(!target||deleting.value)return;deleting.value=true;deleteError.value='';try{await api('/conversations/'+target.id,{method:'DELETE'});drafts.delete(target.id);if(activeId.value===target.id){resetView();quote.value='';remember('');}history.value=history.value.filter(c=>c.id!==target.id);deleteTarget.value=null;await loadHistory();}catch{deleteError.value='删除失败，请重试';}finally{deleting.value=false;}}
function chooseModel(event:Event){const element=event.target as HTMLSelectElement;const id=element.value;element.value=modelId.value;if(props.embedded)emit('modelChoice',id);else modelId.value=id;}
watch(()=>[props.embedded,props.defaultModelId],()=>{if(props.embedded && props.profiles.some(p=>p.id===props.defaultModelId))modelId.value=props.defaultModelId!;},{immediate:true});
const drafts=new Map<string,string>();
const composing=ref(false);let lastAppliedAt='';let pendingEcho:{message:Message;index:number}|null=null;
function composerKeydown(event:KeyboardEvent){if(event.key==='Enter' && !event.shiftKey && !event.isComposing && !composing.value && event.keyCode!==229){event.preventDefault();if(!event.repeat)void send();}}

const filteredHistory=computed(()=>history.value.filter(c=>(c.title+' '+c.preview).toLowerCase().includes(historyQuery.value.trim().toLowerCase())));
function remember(id:string){try{localStorage.setItem('assistant-active-global',id||'new');}catch{}}
function remembered(){try{return localStorage.getItem('assistant-active-global') || localStorage.getItem('assistant-active-'+props.context.runId);}catch{return null;}}
function resetView(){epoch++;lastAppliedAt='';pendingEcho=null;messages.value=[];question.value='';error.value='';remoteBusy.value=false;sending.value=false;initializing.value=false;activeId.value='';activeTitle.value='';}
function apply(data:Conversation){
  // Poll responses may arrive out of order or predate POST persistence.
  if(lastAppliedAt && data.updated_at<lastAppliedAt)return;
  lastAppliedAt=data.updated_at;
  const received=[...data.messages];
  if(pendingEcho){if(received.length<=pendingEcho.index)received.push(pendingEcho.message);else pendingEcho=null;}
  messages.value=received;activeId.value=data.id;activeTitle.value=data.title;remoteBusy.value=data.status==='running'||!!pendingEcho;error.value=data.error||'';
}
let historyRequest=0;
async function loadHistory(){const request=++historyRequest;try{const list=await api<HistoryItem[]>('/conversations');if(request===historyRequest){history.value=list;historyError.value='';}}catch{if(request===historyRequest)historyError.value='历史对话加载失败，请重试';}}
async function toggleHistory(){historyOpen.value=!historyOpen.value;if(historyOpen.value || props.embedded)await loadHistory();}
function newConversation(){drafts.set(activeId.value,question.value);resetView();quote.value='';historyOpen.value=false;historyQuery.value='';remember('');void loadHistory();}
defineExpose({newConversation});
async function openConversation(id:string,keepQuote=false){drafts.set(activeId.value,question.value);resetView();const e=epoch;initializing.value=true;historyOpen.value=false;if(!keepQuote)quote.value='';try{const data=await api<Conversation>('/conversations/'+id);if(e!==epoch)return;apply(data);question.value=drafts.get(id)||'';const last=[...data.messages].reverse().find(m=>m.model_profile_id);if(last && props.profiles.some(p=>p.id===last.model_profile_id)){if(props.embedded)emit('modelChoice',last.model_profile_id!);else modelId.value=last.model_profile_id!;}remember(id);scrollBottom();}catch{if(e===epoch)error.value='对话加载失败，请从历史记录重试';}finally{if(e===epoch)initializing.value=false;}}
watch(()=>props.profiles,()=>{if(!props.profiles.some(p=>p.id===modelId.value))modelId.value=props.profiles.find(p=>p.id===props.defaultModelId)?.id||props.profiles[0]?.id||'';},{immediate:true});
watch(()=>[props.context.runId,props.context.quote],()=>{quote.value=props.context.quote;historyOpen.value=false;},{immediate:true});
async function initializeConversation(){const e=epoch;initializing.value=true;await loadHistory();if(e!==epoch)return;const saved=remembered();const id=saved==='new'?'':history.value.find(c=>c.id===saved)?.id||history.value[0]?.id;if(id)await openConversation(id,true);else initializing.value=false;}
function scrollBottom(){void nextTick(()=>{if(messageList.value)messageList.value.scrollTop=messageList.value.scrollHeight;});}
async function poll(){if(polling)return;polling=true;const e=epoch;const id=activeId.value;try{if(id && remoteBusy.value){const data=await api<Conversation>('/conversations/'+id);if(e===epoch){const changed=data.messages.length!==messages.value.length;apply(data);if(changed)scrollBottom();}}if(historyOpen.value || props.embedded)await loadHistory();}catch{/* The active send or the next poll will refresh the conversation. */}finally{polling=false;}}
onMounted(()=>{timer=setInterval(poll,1000);void initializeConversation();});onBeforeUnmount(()=>{epoch++;if(timer)clearInterval(timer);});
async function send(){
  if(busy.value||initializing.value||!question.value.trim()||!modelId.value)return;
  const e=epoch;const ctx={...props.context};const sentQuote=quote.value;const sentQuestion=question.value.trim();const chosenModel=modelId.value;let id=activeId.value;
  sending.value=true;error.value='';
  pendingEcho={message:{role:'user',content:sentQuestion,quote:sentQuote},index:messages.value.length};
  messages.value.push(pendingEcho.message);question.value='';quote.value='';remoteBusy.value=true;scrollBottom();
  try{
    if(!id){const created=await api<Conversation>('/conversations',{method:'POST',body:JSON.stringify({run_id:ctx.runId||null})});id=created.id;if(e===epoch){activeId.value=id;remember(id);}}
    const data=await api<Conversation>(`/conversations/${id}/messages`,{method:'POST',body:JSON.stringify({run_id:ctx.runId||null,question:sentQuestion,quote:sentQuote,scope:sentQuote?ctx.scope:'research',revision:ctx.revision,model_profile_id:chosenModel})});
    if(e===epoch){apply(data);scrollBottom();}
  }catch(err){if(e===epoch){if(pendingEcho){question.value=sentQuestion;quote.value=sentQuote;}pendingEcho=null;remoteBusy.value=false;if(id){try{const saved=await api<Conversation>('/conversations/'+id);if(e===epoch)apply(saved);}catch{}}if(e===epoch)error.value=err instanceof Error?err.message:'回答失败';}}
  finally{if(e===epoch)sending.value=false;void loadHistory();}
}
function dateLabel(value:string){const date=new Date(value);const today=new Date();if(date.toDateString()===today.toDateString())return '今天';today.setDate(today.getDate()-1);if(date.toDateString()===today.toDateString())return '昨天';return date.toLocaleDateString('zh-CN');}
function timeLabel(value:string){return new Date(value).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});}
</script>
<style scoped>
.chat-panel{width:350px;min-width:300px;height:100%;box-sizing:border-box;display:flex;flex-direction:column;gap:16px;padding:20px;background:white;border-left:1px solid #dce5f4}.chat-panel header{display:flex;align-items:center;justify-content:space-between}.chat-panel h3{margin:0;font-size:18px;color:#24334d}button{border:1px solid #d7e1f3;background:#edf3ff;border-radius:7px;padding:8px 12px;color:#3767c5;cursor:pointer}.chat-messages{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column;gap:12px}.chat-welcome{flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;min-height:180px}.assistant-logo{width:66px;height:66px;border-radius:20px;background:linear-gradient(140deg,#367aff,#7948ed);color:white;display:grid;place-items:center;font-size:52px;box-shadow:0 8px 24px #4d76f42b}.chat-welcome h2{font-size:23px;margin:20px 0 10px;color:#23344d}.chat-welcome p{color:#7c8ba4;font-size:13px;margin:0}.message{padding:12px;border:1px solid #e2e8f2;border-radius:12px;font-size:14px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}.message p{margin:0}.message small{display:block;color:#72819a;font-size:11px;max-height:70px;overflow:auto;margin-bottom:7px}.message .model-caption{margin:8px 0 0}.user{background:#e8f0ff}.error{font-size:12px;color:#ba3545}.quote-preview{margin:0;background:#edf4ff;padding:10px 12px;border-radius:10px;font-size:13px;max-height:150px;overflow:auto;border-left:3px solid #86aaff}.quote-preview p{margin:5px 0;line-height:1.6;overflow-wrap:anywhere}.quote-preview button{border:0;background:transparent;padding:0 4px}.quote-preview small{color:#5f7fae}form{display:flex;flex-direction:column;gap:10px;flex-shrink:0}textarea{width:100%;box-sizing:border-box;border:1px solid #d5def0;border-radius:10px;padding:12px;resize:vertical;max-height:220px;min-height:80px;font:inherit}.composer-actions{display:flex;align-items:center;gap:8px;justify-content:space-between}.composer-actions select{min-width:0;max-width:calc(100% - 82px);border:1px solid #d7e1f3;border-radius:8px;padding:9px;background:#f8faff;color:#344967}.send{background:#3975ff;color:white;flex-shrink:0}button:disabled{opacity:.5}.model-hint{color:#8999b1;font-size:11px}
</style>

<style scoped>
.chat-panel{position:relative}.header-actions{display:flex;align-items:center;gap:7px}.header-actions button{width:32px;height:32px;padding:0;display:grid;place-items:center;background:#f8faff;font-size:20px}.header-actions .selected{background:#e2ebff;color:#3568eb}.conversation-title{display:flex;align-items:center;gap:10px;font-size:14px;font-weight:600;color:#20242b;padding:4px 0 14px;background:transparent;border-bottom:1px solid #111;margin:0;flex-shrink:0}.conversation-title span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.conversation-folder{flex-shrink:0}.history-backdrop{position:absolute;inset:60px 0 0;background:#25364c26;z-index:10}.chat-history{position:absolute;z-index:11;top:60px;left:14px;right:14px;max-height:70%;display:flex;flex-direction:column;gap:12px;border:1px solid #dce5f5;border-radius:14px;padding:16px;background:white;box-shadow:0 8px 28px #253a5b20;box-sizing:border-box}.chat-history h4{margin:0;font-size:16px;color:#25354c}.chat-history>small{color:#8392a9;font-size:11px}.chat-history header button{border:0;padding:2px 5px;background:transparent}.chat-history input{min-width:0;border:1px solid #d9e3f4;border-radius:8px;padding:9px;font:inherit;font-size:13px}.conversation-list{overflow:auto;min-height:0}.history-date{font-size:12px;color:#8191ab;margin:10px 4px}.conversation-row{display:grid;grid-template-columns:minmax(0,1fr) auto;text-align:left;width:100%;gap:6px;border:1px solid transparent;border-radius:9px;padding:10px;margin-bottom:6px;background:white;color:#32445f}.conversation-row.active{background:#ebf2ff;border-left:3px solid #477aff}.conversation-row strong{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.conversation-row time{font-size:11px;color:#7b8eab}.conversation-row span{grid-column:1/-1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px;color:#7b8eab}.conversation-row small{grid-column:1/-1;font-size:11px;color:#8a98af}.history-empty{font-size:12px;color:#8795ab}.model-caption{overflow-wrap:anywhere}.chat-header{flex-shrink:0}
</style>

<style scoped>
.history-item{position:relative}.history-item .conversation-row{padding-right:36px}.delete-conversation{position:absolute;right:5px;bottom:8px;padding:2px 6px;background:transparent;border:0;font-size:18px;color:#7b8eab}.delete-conversation:hover{color:#c63e48;background:#fff0f1}.delete-overlay{position:absolute;inset:0;z-index:20;background:#25364c55;display:flex;align-items:center;justify-content:center;padding:16px}.delete-dialog{background:white;border-radius:14px;padding:20px;max-width:360px;box-shadow:0 10px 30px #25364c33}.delete-dialog h4{margin:0;color:#25354c}.delete-dialog p{font-size:13px;line-height:1.7;overflow-wrap:anywhere}.delete-dialog>div{display:flex;justify-content:flex-end;gap:10px}.cancel-delete{background:#e8f6ee;color:#23814f;border-color:#b9dfca}.confirm-delete{background:#d7424c;color:white;border-color:#d7424c}
</style>

<style scoped>
.chat-model-label{display:flex;align-items:center;gap:10px;min-width:0;max-width:calc(100% - 82px)}.chat-model-label select{max-width:100%;min-width:0}.embedded{width:100%;min-width:0;height:100%;padding:24px;border:0;background:transparent;gap:20px}.embedded .chat-header h3{font-size:24px}.embedded .header-actions button{width:auto;min-width:110px;font-size:14px;padding:8px 14px;background:white}.embedded .conversation-title{font-size:16px;padding-bottom:15px}.embedded .chat-messages{padding:4px 4px 12px;gap:20px}.embedded .message{flex-shrink:0;background:white;max-width:88%;padding:16px 20px;box-sizing:border-box}.embedded .message.user{align-self:flex-end;background:#e3edff;max-width:80%}.embedded .message.assistant{align-self:flex-start}.embedded form{padding:16px;border:1px solid #dce5f5;border-radius:18px;background:white}.embedded textarea{min-height:84px;max-height:180px}.embedded .chat-model-label{font-size:13px;color:#40516e}.embedded .chat-model-label span{white-space:nowrap}.embedded .chat-model-label select{min-width:150px;background:white}.embedded .send{background:linear-gradient(120deg,#397aff,#8054f3);padding:12px 20px;border:0}.embedded .chat-welcome{min-height:100px}.embedded-history{position:static;inset:auto;z-index:auto;max-height:none;height:100%;min-height:0;width:100%;padding:0;border:0;box-shadow:none;border-radius:0;background:transparent;gap:10px}.embedded-history h4{font-size:14px;color:#33425e}.embedded-history header{display:flex;align-items:center;justify-content:space-between}.embedded-history header span{font-size:12px;color:#8a97ad}.embedded-history .conversation-list{flex:1;min-height:70px}.embedded-history .conversation-row{margin-bottom:6px;padding:10px 30px 10px 8px;gap:5px}.embedded-history .conversation-row span{display:none}.embedded-history .conversation-row strong{font-weight:500}.embedded-history .conversation-row small{font-size:11px}.history-local-hint{font-size:12px;color:#8a97ad;margin:0;padding-top:3px}
</style>
