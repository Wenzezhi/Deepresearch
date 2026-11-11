<template>
  <div class="document-card">
    <header class="document-header"><h3>{{ title }}</h3><div class="document-actions"><slot name="actions"/><button class="copy-document" type="button" :aria-label="`复制${title}`" :title="`复制${title}完整正文`" :disabled="!markdown.trim()" @click="copy"><UiIcon :name="state==='copied'?'check':'copy'"/><span>{{ state==='copied'?'已复制':state==='error'?'复制失败':'复制' }}</span></button></div></header>
    <div ref="body" class="markdown-body" v-html="html" @mouseup="selectText" @keyup="selectText"></div>
    <Teleport to="body"><div v-if="selection" class="selection-actions" :style="{left:selection.x+'px',top:selection.y+'px'}" @mousedown.prevent><button :disabled="savingMark" :aria-label="removingMark?'取消高亮':'添加高亮'" :title="removingMark?'取消这段高亮':'标记选中文字'" @click="highlight"><span :class="{'light-off':removingMark}">🖍 Light</span></button><button @click="chat">▢ chat</button></div></Teleport>
    <p v-if="readingError" class="reading-error" role="alert">{{ readingError }}</p>
    <span role="status" class="copy-status">{{ state==='error'?'复制失败，请检查剪贴板权限后重试。':state==='copied'?'已复制完整正文':'' }}</span>
  </div>
</template>
<script setup lang="ts">
import {computed,onMounted,onBeforeUnmount,ref,watch} from 'vue';
import {marked} from 'marked';
import DOMPurify from 'dompurify';
import UiIcon from './UiIcon.vue';
import {api} from '../services/api';
import type {ChatContext} from './ChatPanel.vue';
const props=defineProps<{title:string;markdown:string;runId?:string;scope?:string;revision?:number}>();
const emit=defineEmits<{chat:[context:ChatContext]}>();
const marks=ref<{start:number;end:number;text:string}[]>([]);const readingError=ref('');
const selection=ref<{start:number;end:number;text:string;x:number;y:number}|null>(null);
const documentKey=computed(()=>{let h=2166136261;for(const c of props.markdown)h=Math.imul(h^c.charCodeAt(0),16777619);return `content-${props.scope||'report'}-${(h>>>0).toString(16)}`;});
let readingEpoch=0;
watch(()=>[props.runId,documentKey.value],async()=>{const e=++readingEpoch;marks.value=[];selection.value=null;readingError.value='';if(!props.runId)return;try{const data=await api<{marks:typeof marks.value}>(`/reading/${props.runId}/${documentKey.value}`);if(e===readingEpoch)marks.value=data.marks;}catch{if(e===readingEpoch)readingError.value='高亮加载失败';}},{immediate:true});
function selectText(){if(!props.runId||!body.value)return;const selected=window.getSelection();if(!selected||selected.isCollapsed||!selected.rangeCount){selection.value=null;return}const range=selected.getRangeAt(0);if(!body.value.contains(range.commonAncestorContainer))return;const prefix=range.cloneRange();prefix.selectNodeContents(body.value);prefix.setEnd(range.startContainer,range.startOffset);const start=prefix.toString().length;const text=range.toString();const rect=range.getBoundingClientRect();selection.value={start,end:start+text.length,text,x:Math.min(innerWidth-180,Math.max(8,rect.left)),y:Math.max(8,rect.top-42)};}
// Normalize overlapping marks so selection matches the visible highlighted span.
function normalizedMarks(items:typeof marks.value){const result:typeof marks.value=[];for(const item of [...items].sort((a,b)=>a.start-b.start)){const last=result[result.length-1];if(last && item.start<=last.end){last.end=Math.max(last.end,item.end);last.text=(body.value?.textContent||'').slice(last.start,last.end);}else result.push({...item});}return result;}
const removingMark=computed(()=>!!selection.value && normalizedMarks(marks.value).some(m=>m.start===selection.value!.start && m.end===selection.value!.end));
const savingMark=ref(false);
async function highlight(){if(!selection.value||!props.runId||savingMark.value)return;const e=readingEpoch;const runId=props.runId;const key=documentKey.value;const {start,end,text}=selection.value;const current=normalizedMarks(marks.value);const next=removingMark.value?current.filter(m=>m.start!==start||m.end!==end):normalizedMarks([...current,{start,end,text}]);savingMark.value=true;readingError.value='';try{await api(`/reading/${runId}/${key}/marks`,{method:'PUT',body:JSON.stringify({marks:next})});if(e===readingEpoch){marks.value=next;selection.value=null;window.getSelection()?.removeAllRanges();}window.dispatchEvent(new CustomEvent('reading-marks-updated',{detail:{runId,key,marks:next}}));}catch{if(e===readingEpoch)readingError.value='高亮保存失败，请重试';}finally{savingMark.value=false;}}
function syncMarks(event:Event){const d=(event as CustomEvent).detail;if(d.runId===props.runId && d.key===documentKey.value){readingEpoch++;marks.value=d.marks;selection.value=null;}}
function clearSelection(){selection.value=null;}
function selectionChanged(){const s=window.getSelection();if(!s?.rangeCount||s.isCollapsed||!body.value?.contains(s.getRangeAt(0).commonAncestorContainer))clearSelection();}
onMounted(()=>{window.addEventListener('reading-marks-updated',syncMarks);document.addEventListener('selectionchange',selectionChanged);window.addEventListener('scroll',clearSelection,true);});
onBeforeUnmount(()=>{readingEpoch++;window.removeEventListener('reading-marks-updated',syncMarks);document.removeEventListener('selectionchange',selectionChanged);window.removeEventListener('scroll',clearSelection,true);});
function chat(){if(!selection.value||!props.runId)return;emit('chat',{runId:props.runId,document:documentKey.value,scope:props.scope||'report',revision:props.revision||0,quote:selection.value.text});selection.value=null;}

const body=ref<HTMLElement|null>(null);
const state=ref<'idle'|'copied'|'error'>('idle');let resetTimer:ReturnType<typeof setTimeout>|undefined;let version=0;
const html=computed(()=>{
  const parsed=marked.parse(props.markdown,{async:false,gfm:true});
  const clean=DOMPurify.sanitize(parsed,{USE_PROFILES:{html:true},FORBID_TAGS:['style','form','input','button','iframe','img','video','audio'],FORBID_ATTR:['style','id','name'],ALLOW_DATA_ATTR:false});
  const template=document.createElement('template');template.innerHTML=clean;
  template.content.querySelectorAll('a').forEach(a=>{const href=a.getAttribute('href')||'';if(!/^(https?:\/\/|mailto:|#)/i.test(href)){a.removeAttribute('href');}else{a.target='_blank';a.rel='noopener noreferrer';}});
  if(marks.value.length){
    const walker=document.createTreeWalker(template.content,NodeFilter.SHOW_TEXT);const nodes:Text[]=[];while(walker.nextNode())nodes.push(walker.currentNode as Text);let offset=0;
    for(const node of nodes){const text=node.data;const base=offset;offset+=text.length;const ranges=marks.value.filter(m=>m.start<offset&&m.end>base).map(m=>({start:Math.max(0,m.start-base),end:Math.min(text.length,m.end-base)})).sort((a,b)=>a.start-b.start);if(!ranges.length)continue;const merged:{start:number;end:number}[]=[];for(const r of ranges){const last=merged[merged.length-1];if(last&&r.start<=last.end)last.end=Math.max(last.end,r.end);else merged.push({...r});}const fragment=document.createDocumentFragment();let pos=0;for(const r of merged){fragment.append(text.slice(pos,r.start));const mark=document.createElement('mark');mark.textContent=text.slice(r.start,r.end);fragment.append(mark);pos=r.end;}fragment.append(text.slice(pos));node.replaceWith(fragment);}
  }
  return template.innerHTML;
});
watch(()=>[props.markdown,props.title],()=>{version++;state.value='idle';if(resetTimer)clearTimeout(resetTimer);});
function fallbackCopy(text:string){const focus=document.activeElement as HTMLElement|null;const area=document.createElement('textarea');area.value=text;area.style.cssText='position:fixed;left:-9999px;top:0';document.body.appendChild(area);try{area.select();if(!document.execCommand('copy'))throw new Error('Copy rejected');}finally{area.remove();focus?.focus({preventScroll:true});}}
async function copy(){const text=body.value?.innerText?.trim();if(!text)return;const current=version;try{try{if(!navigator.clipboard)throw new Error('Clipboard unavailable');await navigator.clipboard.writeText(text);}catch{fallbackCopy(text);}if(current===version)state.value='copied';}catch{if(current===version)state.value='error';}finally{if(current===version){if(resetTimer)clearTimeout(resetTimer);resetTimer=setTimeout(()=>state.value='idle',2500);}}}
onBeforeUnmount(()=>{version++;if(resetTimer)clearTimeout(resetTimer);});
</script>
<style scoped>
.document-card{min-width:0}.document-header{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:20px}.document-header h3{margin:0;font-size:18px;color:#243047}.copy-document{display:inline-flex;gap:6px;align-items:center;flex-shrink:0;border:1px solid transparent;background:transparent;color:#6f809e;border-radius:7px;padding:6px 8px;cursor:pointer;font-size:12px}.copy-document:hover{background:#edf3ff;border-color:#d8e3f8;color:#3163c8}.copy-document:disabled{opacity:.4;cursor:default}.markdown-body{font-family:inherit;font-size:15px;line-height:1.85;color:#34415a;overflow-wrap:anywhere;min-width:0}.markdown-body :deep(> :first-child){margin-top:0}.markdown-body :deep(> :last-child){margin-bottom:0}.markdown-body :deep(h1),.markdown-body :deep(h2),.markdown-body :deep(h3),.markdown-body :deep(h4){color:#172642;line-height:1.5;margin:24px 0 12px;font-weight:650}.markdown-body :deep(h1){font-size:25px}.markdown-body :deep(h2){font-size:21px}.markdown-body :deep(h3){font-size:18px}.markdown-body :deep(p){margin:12px 0}.markdown-body :deep(ul),.markdown-body :deep(ol){padding-left:25px;margin:12px 0}.markdown-body :deep(li){margin:6px 0}.markdown-body :deep(strong){color:#223553;font-weight:650}.markdown-body :deep(a){color:#3269e8;text-decoration:none}.markdown-body :deep(a:hover){text-decoration:underline}.markdown-body :deep(table){display:block;max-width:100%;overflow-x:auto;border-collapse:collapse;margin:18px 0;font-size:14px}.markdown-body :deep(th),.markdown-body :deep(td){border:1px solid #dfe6f1;padding:9px 13px;min-width:90px;text-align:left}.markdown-body :deep(th){background:#f0f5fc;color:#2b4166}.markdown-body :deep(tr:nth-child(even)){background:#f9fbff}.markdown-body :deep(blockquote){margin:16px 0;padding:8px 16px;border-left:3px solid #9bb8f3;background:#f5f8ff;color:#63718c}.markdown-body :deep(code){background:#eef2f8;border-radius:4px;padding:2px 5px;font-size:.9em}.markdown-body :deep(pre){overflow-x:auto;padding:16px;background:#f4f6fa;border:1px solid #e4e9f2;border-radius:9px;line-height:1.6;white-space:pre}.markdown-body :deep(pre code){background:none;padding:0}.markdown-body :deep(hr){border:0;border-top:1px solid #e5eaf2;margin:24px 0}.copy-status{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
</style>

<style scoped>.document-actions{display:flex;align-items:center;gap:8px}.markdown-body :deep(mark){background:#fff059;color:inherit}.selection-actions{position:fixed;z-index:1000;display:flex;gap:4px;border:1px solid #dce5f3;background:white;border-radius:8px;padding:5px;box-shadow:0 4px 20px #18264025}.selection-actions button{border:0;background:#f0f5ff;color:#315a9a;border-radius:5px;padding:7px 12px;cursor:pointer}.reading-error{color:#b83c48;font-size:12px}</style>
<style scoped>.light-off{position:relative;display:inline-block}.light-off:after{content:"";position:absolute;left:42%;top:-12%;height:125%;width:2px;background:currentColor;transform:rotate(32deg)}.selection-actions button:disabled{opacity:.5;cursor:wait}</style>
