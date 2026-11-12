<template><div class="reading-document">
<div v-if="stale" class="report-update-notice" role="status">{{ loading?'正在更新研究，未修改任务保持不变；完成后刷新最终报告。':'最终报告待更新，当前显示上一次生成的报告。' }}</div>
<section v-if="kind==='report'" class="report-block">
  <MarkdownDocument
    title="最终报告"
    :markdown="report"
    :run-id="runId"
    scope="report"
    :revision="revision"
    @chat="emit('chat',$event)"
  >
    <template #actions>
      <ReportExport
        :markdown="report"
        title="研究报告"
      />
      <button
        class="note-action"
        @click="emit('note')"
      >
        Note
      </button>
    </template>
  </MarkdownDocument>
</section>
          <article class="task-detail" v-else-if="task">
            <div class="detail-tabs" role="tablist" aria-label="子任务详情">
              <button :id="pane+'-analysis-tab'" type="button" role="tab" :aria-selected="detailTab==='analysis'" :aria-controls="pane+'-analysis-panel'" :tabindex="detailTab==='analysis'?0:-1" @click="detailTab='analysis'" @keydown.right.prevent="detailTab='tools'; (($event.currentTarget as HTMLElement).nextElementSibling as HTMLElement)?.focus()">分析内容</button>
              <button :id="pane+'-tools-tab'" type="button" role="tab" :aria-selected="detailTab==='tools'" :aria-controls="pane+'-tools-panel'" :tabindex="detailTab==='tools'?0:-1" @click="detailTab='tools'" @keydown.left.prevent="detailTab='analysis'; (($event.currentTarget as HTMLElement).previousElementSibling as HTMLElement)?.focus()">工具调用记录</button>
            </div>
            <div class="analysis-panel" :id="pane+'-analysis-panel'" role="tabpanel" :aria-labelledby="pane+'-analysis-tab'" v-show="detailTab==='analysis'">
            <header class="task-header">
              <div>
                <p class="muted" v-if="task.intent">
                  {{ task.intent }}
                </p>
              </div>
              <div class="task-chip-group">
                <span class="task-label">查询：{{ task.query || "" }}</span>
                <span
                  v-if="task.noteId"
                  class="task-label note-chip"
                  :title="task.noteId"
                >
                  笔记：{{ task.noteId }}
                </span>
                <span
                  v-if="task.notePath"
                  class="task-label note-chip path-chip"
                  :title="task.notePath"
                >
                  <span class="path-label">路径：</span>
                  <span class="path-text">{{ task.notePath }}</span>
                  <button
                    class="chip-action"
                    type="button"
                    @click="emit('copyPath',task.notePath)"
                  >
                    复制
                  </button>
                </span>
              </div>
            </header>

            <section v-if="task && task.notices.length" class="task-notices">
              <h4>系统提示</h4>
              <ul>
                <li v-for="(notice, idx) in task.notices" :key="`${notice}-${idx}`">
                  {{ notice }}
                </li>
              </ul>
            </section>

            <section
              class="sources-block"
              :class="{ 'block-highlight': sourcesHighlight }"
            >
              <h3>最新来源</h3>
              <template v-if="task.sourceItems.length">
                <ul class="sources-list">
                  <li
                    v-for="(item, index) in task.sourceItems"
                    :key="`${item.title}-${index}`"
                    class="source-item"
                  >
                    <a
                      class="source-link"
                      :href="sourceHref(item.url)"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {{ item.title || item.url || `来源 ${index + 1}` }}
                    </a>
                    <div v-if="item.snippet || item.raw" class="source-tooltip">
                      <p v-if="item.snippet">{{ item.snippet }}</p>
                      <p v-if="item.raw" class="muted-text">{{ item.raw }}</p>
                    </div>
                  </li>
                </ul>
              </template>
              <p v-else class="muted">暂无可用来源</p>
            </section>

            <section
              class="summary-block"
              :class="{ 'block-highlight': summaryHighlight }"
            >
              <MarkdownDocument v-if="summary" title="任务总结" :markdown="summary" :run-id="runId" :scope="String(task.id)" :revision="revision" @chat="emit('chat',$event)" /><p v-else class="muted" role="status">{{ summaryPlaceholder }}</p>
            </section>

            </div>
            <section :id="pane+'-tools-panel'" role="tabpanel" :aria-labelledby="pane+'-tools-tab'"
              class="tools-block"
              :class="{ 'block-highlight': toolHighlight }"
              v-show="detailTab==='tools'"
            >
              <p v-if="!task.toolCalls.length" class="muted">当前子任务暂无工具调用记录。</p>
              <ul class="tool-list">
                <li
                  v-for="entry in task.toolCalls"
                  :key="`${entry.eventId}-${entry.timestamp}`"
                  class="tool-entry"
                >
                  <div class="tool-entry-header">
                    <span class="tool-entry-title">
                      #{{ entry.eventId }} {{ entry.agent }} → {{ entry.tool }}
                    </span>
                    <span
                      v-if="entry.noteId"
                      class="tool-entry-note"
                    >
                      笔记：{{ entry.noteId }}
                    </span>
                  </div>
                  <p v-if="entry.notePath" class="tool-entry-path">
                    笔记路径：
                    <button
                      class="link-btn"
                      type="button"
                      @click="emit('copyPath',entry.notePath)"
                    >
                      复制
                    </button>
                    <span class="path-text">{{ entry.notePath }}</span>
                  </p>
                  <p class="tool-subtitle">参数</p>
                  <pre class="tool-pre">{{ formatToolParameters(toolMetadata(entry.parameters) as Record<string, unknown>) }}</pre>
                  <template v-if="entry.result">
                    <p class="tool-subtitle">执行结果</p>
                    <pre class="tool-pre">{{ formatToolResult(entry.result) }}</pre>
                  </template>
                </li>
              </ul>
            </section>
          </article>
<p v-else class="muted">当前任务已移除或尚未生成。</p>
</div></template>
<script setup lang="ts">
import {computed} from 'vue';
import MarkdownDocument from './MarkdownDocument.vue';

import ReportExport from './ReportExport.vue';

import {publicAnswer,toolMetadata} from '../services/publicAnswer';
import type {ChatContext} from './ChatPanel.vue';
import type {TodoTaskView} from '../services/researchView';
const props=withDefaults(defineProps<{kind:'report'|'task';pane:string;task?:TodoTaskView|null;report?:string;runId?:string;revision?:number;detail?:'analysis'|'tools';stale?:boolean;loading?:boolean;sourcesHighlight?:boolean;summaryHighlight?:boolean;toolHighlight?:boolean}>(),{report:'',detail:'analysis'});
const emit=defineEmits<{chat:[context:ChatContext];copyPath:[path:string|null];note:[];'update:detail':[tab:'analysis'|'tools']}>();

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'; function sourceHref(url: string) {const localPrefix = 'local://documents/'; if (url.startsWith(localPrefix)) {const documentId = url.slice(localPrefix.length); return `${apiBase}/documents/${encodeURIComponent(documentId)}/download`;} return url || '#';}

const detailTab=computed({get:()=>props.detail,set:value=>emit('update:detail',value)});
const summary=computed(()=>props.task?.status==='completed'?publicAnswer(props.task.summary):'');
const summaryPlaceholder=computed(()=>props.task?.status==='in_progress'?'正在整理研究结论，完成后展示正式总结。':props.task?.status==='pending'?'等待子任务执行。':'暂无可展示的正式总结。');
function formatToolParameters(parameters:Record<string,unknown>){try{return JSON.stringify(parameters,null,2);}catch{return Object.entries(parameters).map(([key,value])=>`${key}: ${String(value)}`).join('\n');}}
function formatToolResult(result:string){try{return JSON.stringify(toolMetadata(JSON.parse(result)),null,2);}catch{return publicAnswer(result).slice(0,900)||'工具调用已返回。';}}
</script>
<style scoped>
.task-detail{
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 18px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.5);
}
.task-header{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
}
.task-chip-group{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.task-header h3{
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}
.task-header .muted{
  margin: 6px 0 0;
}
.task-label{
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(191, 219, 254, 0.32);
  border: 1px solid rgba(59, 130, 246, 0.35);
  font-size: 12px;
  color: #1e3a8a;
}
.task-label.note-chip{
  background: rgba(34, 197, 94, 0.2);
  border-color: rgba(34, 197, 94, 0.35);
  color: #15803d;
}
.task-label.path-chip{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 360px;
  background: rgba(56, 189, 248, 0.2);
  border-color: rgba(56, 189, 248, 0.35);
  color: #0369a1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.path-label{
  font-weight: 500;
}
.path-text{
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chip-action{
  border: none;
  background: rgba(56, 189, 248, 0.2);
  color: #0369a1;
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}
.chip-action:hover{
  background: rgba(14, 165, 233, 0.28);
  color: #0f172a;
}
.task-notices{
  background: rgba(191, 219, 254, 0.28);
  border: 1px solid rgba(96, 165, 250, 0.35);
  border-radius: 16px;
  padding: 14px 18px;
  color: #1f2937;
}
.task-notices h4{
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}
.task-notices ul{
  list-style: disc;
  margin: 0 0 0 18px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.task-notices li{
  font-size: 13px;
}
.summary-block .block-pre,
.sources-block .block-pre{
  max-height: 360px;
}
.tools-block{
  position: relative;
  margin-top: 16px;
  padding: 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.4);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.tools-block h3{
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: 0.02em;
}
.tool-list{
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.tool-entry{
  background: rgba(248, 250, 252, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tool-entry-header{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}
.tool-entry-title{
  font-weight: 600;
  color: #1f2937;
}
.tool-entry-note{
  font-size: 12px;
  color: #0f766e;
}
.tool-entry-path{
  margin: 0;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #2563eb;
}
.tool-subtitle{
  margin: 0;
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}
.tool-pre{
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular,
    Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1f2937;
  background: rgba(248, 250, 252, 0.9);
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  overflow: auto;
  max-height: 260px;
  scrollbar-width: thin;
  scrollbar-color: rgba(129, 140, 248, 0.6) rgba(226, 232, 240, 0.7);
}
.tool-pre::-webkit-scrollbar{
  width: 6px;
}
.tool-pre::-webkit-scrollbar-track{
  background: rgba(226, 232, 240, 0.7);
}
.tool-pre::-webkit-scrollbar-thumb{
  background: rgba(99, 102, 241, 0.7);
  border-radius: 10px;
}
.link-btn{
  background: none;
  border: none;
  color: #0369a1;
  cursor: pointer;
  padding: 0 4px;
  font-size: 12px;
  border-radius: 8px;
  transition: color 0.2s ease, background 0.2s ease;
}
.link-btn:hover{
  color: #0ea5e9;
  background: rgba(14, 165, 233, 0.16);
}
.sources-block,
.summary-block{
  position: relative;
  margin-top: 16px;
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.4);
}
.block-highlight{
  animation: glow 1.2s ease;
}
.sources-block h3,
.summary-block h3{
  margin: 0 0 14px;
  color: #1f2937;
  letter-spacing: 0.02em;
}
.sources-list{
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.source-item{
  position: relative;
  display: inline-flex;
  flex-direction: column;
  gap: 6px;
}
.source-link{
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
  letter-spacing: 0.01em;
  transition: color 0.2s ease;
}
.source-link::after{
  content: " ↗";
  font-size: 12px;
  opacity: 0.6;
}
.source-link:hover{
  color: #0f172a;
}
.source-tooltip{
  display: none;
  position: absolute;
  bottom: calc(100% + 12px);
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255, 255, 255, 0.98);
  color: #1f2937;
  padding: 14px 16px;
  border-radius: 16px;
  box-shadow: 0 18px 32px rgba(15, 23, 42, 0.18);
  width: min(420px, 90vw);
  z-index: 20;
  border: 1px solid rgba(148, 163, 184, 0.24);
}
.source-tooltip::after{
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border-width: 10px;
  border-style: solid;
  border-color: rgba(255, 255, 255, 0.98) transparent transparent transparent;
}
.source-tooltip::before{
  content: "";
  position: absolute;
  bottom: -12px;
  left: 50%;
  transform: translateX(-50%);
  border-width: 12px 10px 0 10px;
  border-style: solid;
  border-color: rgba(255, 255, 255, 0.98) transparent transparent transparent;
  filter: drop-shadow(0 -2px 4px rgba(15, 23, 42, 0.12));
}
.source-tooltip p{
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.6;
}
.source-tooltip p:last-child{
  margin-bottom: 0;
}
.muted-text{
  color: #64748b;
}
.source-item:hover .source-tooltip,
.source-item:focus-within .source-tooltip{
  display: block;
}
.reading-document{padding:24px;min-width:0;box-sizing:border-box;min-height:calc(100% - 61px);background:white;color:#1f2937}.task-detail{padding:0;border:0;box-shadow:none;border-radius:0;min-width:0;background:transparent}.report-block{margin:0;padding:0;min-width:0}.analysis-panel{display:flex;flex-direction:column;gap:20px;min-width:0}.task-label{overflow-wrap:anywhere;max-width:100%;box-sizing:border-box}.task-label.path-chip{max-width:min(360px,100%)}.sources-block,.summary-block{min-width:0}.source-link{overflow-wrap:anywhere}.detail-tabs{display:flex;align-items:center;gap:12px;margin-bottom:6px;min-width:0}.detail-tabs button{font-size:13px;border:0;border-radius:18px;padding:8px 16px;background:#f1f5fc;color:#7a89a4;font-weight:600;cursor:pointer}.detail-tabs button[aria-selected=true]{background:#386cff;color:white}.detail-tabs button:focus-visible{outline:2px solid #9bb8f3;outline-offset:2px}.note-action{border:1px solid #d9e3f3;background:white;color:#3b6cc0;border-radius:7px;padding:6px 12px;cursor:pointer}.muted{line-height:1.6}.source-tooltip{max-width:90%;box-sizing:border-box}@keyframes glow{50%{box-shadow:0 0 0 3px #91b5ff55}}
</style>

<style scoped>.report-update-notice{margin:0 0 20px;padding:12px 16px;border-radius:9px;background:#fff7e4;color:#9b6917;font-size:13px;line-height:1.6}</style>
