<template>
  <main class="app-shell" :class="{ expanded: isExpanded }">
    <div class="aurora" aria-hidden="true">
      <span></span>
      <span></span>
      <span></span>
    </div>

    <!-- 初始状态：居中输入卡片 -->
    <div v-if="!isExpanded" class="layout p0-home">
      <aside class="home-sidebar"><h2>🔍 深度研究助手</h2>
        <div class="home-mode-actions"><button class="new-research-btn" :class="{modeSelected:homeMode==='research'}" @click="startNewResearch">＋ 新研究</button><button class="new-research-btn" :class="{modeSelected:homeMode==='chat'}" :aria-pressed="homeMode==='chat'" @click="openHomeChat"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M21 11a9 9 0 0 1-9 9H4l-3 2 2-6a9 9 0 1 1 18-5Z"/></svg>对话助手</button></div>
        <NoteList :draggable="isExpanded" @drag-note="startNoteDrag" @drag-finish="endDocumentDrag" :notes="personalNotes" @open="openNote" @changed="loadNotes" />
        <HistoryList v-show="homeMode==='research'" :runs="historyRuns" @open="openRun" @rename="renameRun" @delete="deleteRun" />
        <div id="home-conversation-history" v-show="homeMode==='chat'" class="home-conversation-history"></div>
        <p v-if="historyError && homeMode==='research'" class="history-error">{{ historyError }}</p>
      </aside>
      <section v-show="homeMode==='research'" class="panel panel-form panel-centered">
        <header class="panel-head home-welcome">
          <div class="logo">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 2.5c-.7 0-1.4.2-2 .6L4.6 7C3.6 7.6 3 8.7 3 9.9v4.2c0 1.2.6 2.3 1.6 2.9l5.4 3.9c1.2.8 2.8.8 4 0l5.4-3.9c1-.7 1.6-1.7 1.6-2.9V9.9c0-1.2-.6-2.3-1.6-2.9L14 3.1a3.6 3.6 0 0 0-2-.6Z"
              />
            </svg>
          </div>
          <div>
            <h1>深度研究助手</h1>
            <p>需要帮你搜索什么？</p>
          </div>
        </header>

        <div class="home-composer">
        <form class="form" @submit.prevent="handleSubmit">
          <label class="field">
            <span>研究主题</span>
            <textarea
              v-model="form.topic"
              placeholder="例如：探索多模态模型在 2025 年的关键突破"
              rows="4"
              required
            ></textarea>
          </label>

          <section class="options">
            <label class="field option"><span>研究模型</span><select aria-label="研究模型" :value="form.modelProfileId" @change="selectResearchModel" required><option value="" disabled>请选择或新增模型配置</option><option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
            <label class="field option">
              <span>搜索引擎</span>
              <select v-model="form.searchApi">
                <option value="">沿用后端配置</option>
                <option
                  v-for="option in searchOptions"
                  :key="option"
                  :value="option"
                >
                  {{ option }}
                </option>
              </select>
            </label>
          </section>

          <LocalDocumentPicker
            v-model:selected-ids="selectedDocumentIds"
            :disabled="submitting"
          />

          <p class="hint muted">开始后，本次研究的模型配置将固定。</p>
          <p v-if="profileLoadError" role="alert" class="error-chip">{{ profileLoadError }}</p>
          <div class="form-actions">
            <button class="submit" type="submit" :disabled="submitting">
              <span class="submit-label">
                <svg
                  v-if="loading"
                  class="spinner"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="9" stroke-width="3" />
                </svg>
                {{ submitting ? "正在创建…" : "开始研究" }}
              </span>
            </button>

          </div>
        </form>

        <p v-if="error" class="error-chip">
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M10 3.2c-.3 0-.6.2-.8.5L3.4 15c-.4.7.1 1.6.8 1.6h11.6c.7 0 1.2-.9.8-1.6L10.8 3.7c-.2-.3-.5-.5-.8-.5Zm0 4.3c.4 0 .7.3.7.7v4c0 .4-.3.7-.7.7s-.7-.3-.7-.7V8.2c0-.4.3-.7.7-.7Zm0 6.6a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"
            />
          </svg>
          {{ error }}
        </p>
        <p v-else-if="loading" class="hint muted">
          正在收集线索与证据，实时进展见右侧区域。
        </p>
        </div>
      </section>
      <section v-show="homeMode==='chat'" class="home-chat-panel" aria-label="首页对话区"><div id="home-chat-slot"></div></section>
      <ModelConfig ref="modelConfig" :profiles="profiles" :selected-id="form.modelProfileId" @select="form.modelProfileId=$event" @changed="loadProfiles" />
    </div>

    <div v-if="workspaceNotes.length && !isExpanded" class="home-note-overlay"><nav><button v-for="entry in workspaceNotes" :key="entry.key" :class="{active:entry.key===activeLeftNote}" @click="activateLeftNote(entry.key)">Note · {{ entry.note.title }} <span @click.stop="requestCloseNote(entry.key)">×</span></button></nav><div id="home-note-slot"></div></div>
    <!-- 全屏状态：左右分栏布局 -->
    <div v-if="isExpanded" class="layout layout-fullscreen" :style="layoutWidths">
      <!-- 左侧：研究信息 -->
      <aside class="sidebar">
        <div class="sidebar-header">
          <button class="back-btn" @click="goBack">
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path d="M19 12H5M12 19l-7-7 7-7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            返回
          </button>
          <h2>🔍 深度研究助手</h2>
        </div>

        <div class="sidebar-scroll">
        <div class="research-info">
          <div class="info-item">
            <label class="topic-label">研究主题<button :disabled="loading || actionBusy" aria-label="修改研究主题" @click="editTopic"><UiIcon name="edit"/></button></label>
            <p class="topic-display">{{ form.topic }}</p>
          </div>

          <div class="info-item" v-if="form.searchApi">
            <label>搜索引擎</label>
            <p>{{ form.searchApi }}</p>
          </div>

          <div class="info-item" v-if="totalTasks > 0">
            <label>研究进度</label>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: `${(completedTasks / totalTasks) * 100}%` }"></div>
            </div>
            <p class="progress-text">{{ completedTasks }} / {{ totalTasks }} 任务完成</p>
          </div>
        </div>

        <TimingPanel :run="selectedRun" :tasks="todoTasks" :busy="actionBusy || editingTasks" @control="controlResearch" />
        <NoteList :draggable="isExpanded" @drag-note="startNoteDrag" @drag-finish="endDocumentDrag" :notes="personalNotes" @open="openNote" @changed="loadNotes" /><HistoryList :runs="historyRuns" :selected="selectedRun?.id" @open="openRun" @rename="renameRun" @delete="deleteRun" />
        </div>
        <p v-if="historyError" class="history-error">{{ historyError }}</p>
        <div class="sidebar-actions">
          <button class="new-research-btn" @click="startNewResearch">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
            </svg>
            开始新研究
          </button>
        </div>
      </aside>

      <ResizeHandle label="调整信息栏宽度" :value="columnSizes.sidebar" :min="230" :max="columnSizes.sidebar+columnRoom" @resize="resizeColumn('sidebar',$event)" />
      <!-- 右侧：研究结果 -->
      <section
        class="panel panel-result"
        v-if="todoTasks.length || reportMarkdown || progressLogs.length || error"
      >
        <header class="status-bar">
          <div class="status-main">
            <div class="status-chip" :class="{ active: loading }">
              <span class="dot"></span>
              {{ workflowStatus }}
            </div>
            <span class="status-meta">
              任务进度：{{ completedTasks }} / {{ totalTasks || todoTasks.length || 1 }}
              · 阶段记录 {{ progressLogs.length }} 条
            </span>
          </div>
          <div class="status-controls"><button class="secondary-btn assistant-entry" :aria-expanded="!!chatContext" @click="openChat()">▢ 对话助手</button>
            <button class="secondary-btn" :aria-expanded="!logsCollapsed" aria-controls="research-timeline" @click="logsCollapsed = !logsCollapsed">
              {{ logsCollapsed ? "展开流程" : "收起流程" }}
            </button>
          </div>
        </header>

        <p v-if="error" class="error-chip" role="alert">{{ error }}</p>

        <div id="research-timeline" class="timeline-wrapper" v-show="!logsCollapsed && progressLogs.length">
          <transition-group name="timeline" tag="ul" class="timeline">
            <li v-for="(log, index) in progressLogs" :key="`${log}-${index}`">
              <span class="timeline-node"></span>
              <p>{{ log }}</p>
            </li>
          </transition-group>
        </div>

        <div class="tasks-section" :class="{editing:editingTasks}" v-if="todoTasks.length || (selectedRun && !loading)">
          <TaskEditor v-if="editingTasks" :tasks="todoTasks" :busy="actionBusy" @cancel="editingTasks=false" @save="saveTasks" />
          <aside class="tasks-list" v-else>
            <div class="task-list-head"><h3>任务清单</h3><button aria-label="编辑任务清单" :disabled="loading || actionBusy" @click="editingTasks=true"><UiIcon name="edit"/></button></div>
            <ul>
              <li
                v-for="task in todoTasks"
                :key="task.id"
                :class="['task-item', { active: taskVisible(task.id), completed: task.status === 'completed' }]"
              >
                <div class="task-card-head"><button type="button" class="task-button" @click="selectTask(task.id)"><span class="task-title">{{ task.title }}</span></button>
                  <button v-if="retryable(task)" class="task-status retry-task" :class="task.status" :disabled="actionBusy || editingTasks || task.retryQueued" :aria-label="`重试任务：${task.title}`" :title="loading?'排队重试此任务，不打断其他任务':'仅重新生成此任务，并更新最终报告'" @click.stop="retryTask(task)">{{ task.retryQueued?'重试已排队':formatTaskStatus(task.status)+' ↻' }}</button>
                  <span v-else class="task-status" :class="task.status">{{ formatTaskStatus(task.status) }}</span>
                </div>
                <p class="task-intent">{{ task.intent }}</p>
              </li>
            </ul>
          </aside>

          <ResizeHandle label="调整任务清单宽度" :value="columnSizes.tasks" :min="210" :max="columnSizes.tasks+columnRoom" @resize="resizeColumn('tasks',$event)" />
          <div class="content-shell"><div v-if="editingTasks" class="editing-mask">正在编辑任务，保存后更新研究结果</div><div ref="documentPanes" class="document-panes" :class="{split:!!comparison}" :style="{'--document-left':splitPercent+'%'}"><div ref="researchContent" class="research-content">
            <nav class="research-tabs" role="tablist" aria-label="研究内容" @keydown="navigateResearchTabs">
              <button v-for="entry in leftNotes" :key="entry.key" draggable="true" @dragstart="beginDocumentDrag($event,{kind:'key',key:entry.key})" @dragend="endDocumentDrag" role="tab" :aria-selected="noteActive && activeLeftNote===entry.key" :tabindex="noteActive && activeLeftNote===entry.key?0:-1" @click="activateLeftNote(entry.key)">Note · {{ entry.note.title }} <span role="button" aria-label="关闭 Note" @click.stop="requestCloseNote(entry.key)">×</span></button>
              <button v-if="reportReady && !isOnRight('report')" draggable="true" @dragstart="beginDocumentDrag($event,{kind:'report'})" @dragend="endDocumentDrag" title="可拖动到右侧并排对照" id="report-tab" role="tab" type="button" :aria-selected="reportSelected && !noteActive" :tabindex="reportSelected && !noteActive ? 0 : -1" aria-controls="report-panel" @click="selectReport">最终报告</button>
              <button v-for="task in leftTasks" draggable="true" @dragstart="beginDocumentDrag($event,{kind:'task',id:task.id})" @dragend="endDocumentDrag" title="可拖动到右侧并排对照" :id="`task-tab-${task.id}`" :key="task.id" role="tab" type="button" :aria-selected="!noteActive && !reportSelected && activeTaskId===task.id" :tabindex="!noteActive && !reportSelected && activeTaskId===task.id ? 0 : -1" aria-controls="task-panel" @click="selectTask(task.id)">{{ task.title }}<span class="tab-state" :class="task.status" :title="formatTaskStatus(task.status)"></span></button>
            </nav>
          <div id="left-note-slot" v-show="noteActive"></div>
          <ResearchDocument v-if="!noteActive && ((reportSelected && reportReady) || currentTask)" :id="reportSelected?'report-panel':'task-panel'" role="tabpanel" :aria-labelledby="reportSelected?'report-tab':`task-tab-${activeTaskId}`" :kind="reportSelected && reportReady?'report':'task'" pane="left" :task="currentTask" :report="reportMarkdown" :run-id="selectedRun?.id" :revision="selectedRun?.revision" :detail="currentTask?taskDetailViews[currentTask.id]||'analysis':'analysis'" @update:detail="currentTask && (taskDetailViews[currentTask.id]=$event)" :stale="reportStale" :loading="loading" :sources-highlight="sourcesHighlight" :summary-highlight="summaryHighlight" :tool-highlight="toolHighlight" @chat="openChat" @copy-path="copyNotePath" @note="createNote('left')" />

          <article class="task-detail" v-else-if="!noteActive">
            <p class="muted">{{ leftTasks.length || !comparison ? '等待任务规划或执行结果。' : '此区域暂无标签，可将右侧标签拖回这里。' }}</p>
          </article>
          </div>
          <ResizeHandle v-if="comparison" label="调整对照文档宽度" :value="splitWidth" :min="280" :max="Math.max(280,paneWidth-290)" @resize="setSplitWidth" />
          <section v-if="comparison" class="comparison-pane" aria-label="对照文档">
            <header class="comparison-header"><nav class="research-tabs" role="tablist" aria-label="右侧研究内容" @keydown="navigateResearchTabs"><button v-for="key in rightDocuments" :key="key" :id="'right-tab-'+key" :data-document-key="key" :title="documentTitle(key)" role="tab" :aria-selected="activeRightKey===key" :tabindex="activeRightKey===key?0:-1" draggable="true" @dragstart="beginDocumentDrag($event,{kind:'key',key})" @dragend="endDocumentDrag" @click="activateRight(key)">{{ documentTitle(key) }}<span v-if="key.startsWith('task:')" class="tab-state" :class="documentTask(key)?.status"></span></button></nav><button class="close-comparison" aria-label="关闭对照窗口" title="关闭右侧并将全部标签移回左侧" @click="closeComparison">×</button></header>
            <div id="right-note-slot" v-show="comparison.kind==='note'"></div>
            <ResearchDocument v-if="comparison.kind!=='note'" :id="comparison.kind==='report'?'right-report-panel':'right-task-panel'" role="tabpanel" :aria-labelledby="'right-tab-'+activeRightKey" :kind="comparison.kind==='report'?'report':'task'" pane="right" :task="comparisonTask" :report="reportMarkdown" :run-id="selectedRun?.id" :revision="selectedRun?.revision" :detail="comparisonTask?taskDetailViews[comparisonTask.id]||'analysis':'analysis'" @update:detail="comparisonTask && (taskDetailViews[comparisonTask.id]=$event)" :stale="reportStale" :loading="loading" :sources-highlight="sourcesHighlight" :summary-highlight="summaryHighlight" :tool-highlight="toolHighlight" @chat="openChat" @copy-path="copyNotePath" @note="createNote('right')" />
          </section>
          </div>
          <div v-if="dragDocument && !editingTasks" class="document-drop-overlay"><div class="document-drop-zone drop-left" @dragover.prevent @drop.prevent.stop="dropDocument('left')">放到左侧阅读区</div><div class="document-drop-zone drop-right" @dragover.prevent @drop.prevent.stop="dropDocument('right')">{{ comparison?'移入右侧标签组':'松开以并排对照' }}</div></div>
          <p v-if="comparisonError" class="comparison-error" role="alert">{{ comparisonError }}</p>
          </div>
        </div>
      </section>
      <ResizeHandle v-if="chatContext" label="调整对话助手宽度" :value="columnSizes.chat" :min="300" :max="columnSizes.chat+columnRoom" reverse @resize="resizeColumn('chat',$event)" />
      <div v-if="chatContext" id="research-chat-slot" class="chat-slot"></div>
    </div>
    <Teleport v-for="entry in workspaceNotes" :key="entry.key" :to="!isExpanded?'#home-note-slot':isOnRight(entry.key)?'#right-note-slot':'#left-note-slot'" defer><NoteEditor :ref="el=>setNoteEditor(entry.key,el)" v-show="!isExpanded?activeLeftNote===entry.key:isOnRight(entry.key)?activeRightKey===entry.key:noteActive && activeLeftNote===entry.key" :note="entry.note" @saved="noteSaved(entry.key)" @close="removeNote(entry.key)" /></Teleport>
    <Teleport v-if="chatContext" :to="isExpanded ? '#research-chat-slot' : '#home-chat-slot'" defer><ChatPanel ref="chatPanel" :embedded="!isExpanded" :context="chatContext" :profiles="profiles" @model-choice="modelConfig?.requestSelect($event)" :default-model-id="selectedRun?.profile?.id || form.modelProfileId" @close="chatContext=null" /></Teleport>
    <Teleport to="body"><dialog ref="topicDialog" class="topic-dialog"><h3>修改研究主题</h3><textarea v-model="topicDraft" aria-label="新研究主题" rows="4" maxlength="2000"/><p>保存后将清空原任务与研究结果，重新开始研究。已保存的笔记保留。</p><div><button @click="topicDialog?.close()">取消</button><button class="confirm" :disabled="!topicDraft.trim()" @click="saveTopic">确认并重新研究</button></div></dialog></Teleport>
  </main>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, shallowReactive, ref, watch } from "vue";

import {
  api, type ModelProfile, type ResearchRun, type RunDetail,
  type ResearchStreamEvent
} from "./services/api";

import { publicAnswer } from "./services/publicAnswer";

import ResizeHandle from "./components/ResizeHandle.vue";
import ChatPanel, { type ChatContext } from "./components/ChatPanel.vue";
import NoteEditor from "./components/NoteEditor.vue";
import NoteList from "./components/NoteList.vue";
import { type PersonalNote } from "./services/notes";
import { marked } from "marked";
import TaskEditor from "./components/TaskEditor.vue";
import UiIcon from "./components/UiIcon.vue";
import ModelConfig from "./components/ModelConfig.vue";
import ResearchDocument from "./components/ResearchDocument.vue";
import HistoryList from "./components/HistoryList.vue";
import TimingPanel from "./components/TimingPanel.vue";
import LocalDocumentPicker from "./components/LocalDocumentPicker.vue";

import type {SourceItem, ToolCallLog, TodoTaskView} from "./services/researchView";

const form = reactive({
  topic: "",
  searchApi: "",
  modelProfileId: ""
});

// 本次研究选中的本地文献 ID
const selectedDocumentIds = ref<string[]>([]);

const profiles = ref<ModelProfile[]>([]);
const modelConfig=ref<InstanceType<typeof ModelConfig>|null>(null);
function selectResearchModel(event:Event){const element=event.target as HTMLSelectElement;const id=element.value;element.value=form.modelProfileId;modelConfig.value?.requestSelect(id);}
const profileLoadError = ref('');
async function loadProfiles(selected?: string) {
  try { profiles.value=await api<ModelProfile[]>('/model-profiles');
    if (selected) form.modelProfileId=selected;
    if (!profiles.value.some(p=>p.id===form.modelProfileId)) form.modelProfileId=profiles.value[0]?.id || '';
    profileLoadError.value='';
  } catch(e) {profileLoadError.value=e instanceof Error?e.message:'模型配置加载失败';}
}
onMounted(()=>loadProfiles());
const loading = ref(false);
const error = ref("");
const progressLogs = ref<string[]>([]);
const logsCollapsed = ref(false);
const isExpanded = ref(false);

const todoTasks = ref<TodoTaskView[]>([]);
const activeTaskId = ref<number | null>(null);
const taskDetailViews=reactive<Record<number,'analysis'|'tools'>>({});
const reportMarkdown = ref("");
const reportSelected = ref(false);
const reportStale=ref(false);
const researchContent = ref<HTMLElement | null>(null);
function resetContentScroll() { void nextTick(() => { if (researchContent.value) researchContent.value.scrollTop = 0; }); }
function selectReport() { if(isOnRight('report')){activateRight('report');return;}noteActive.value=false; reportSelected.value = true; resetContentScroll(); }
const reportReady = computed(() => !!reportMarkdown.value.trim());
watch(reportReady, ready => { if (ready) selectReport(); });
function selectTask(id: number) { if(isOnRight('task:'+id)){activateRight('task:'+id);return;}noteActive.value=false; activeTaskId.value = id; reportSelected.value = false; resetContentScroll(); }
function navigateResearchTabs(event: KeyboardEvent) {
  const keys=['ArrowLeft','ArrowRight','Home','End'];
  if (!keys.includes(event.key)) return;
  const tabs=Array.from((event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]'));
  const index=tabs.indexOf(event.target as HTMLButtonElement); if(index<0)return;
  event.preventDefault();
  const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  tabs[next]?.click();tabs[next]?.focus();tabs[next]?.scrollIntoView({block:'nearest',inline:'nearest'});
}

const summaryHighlight = ref(false);
const sourcesHighlight = ref(false);
const reportHighlight = ref(false);
const toolHighlight = ref(false);



const searchOptions = [
  "advanced",
  "duckduckgo",
  "tavily",
  "perplexity",
  "searxng"
];

const TASK_STATUS_LABEL: Record<string, string> = {
  paused: "已暂停",
  pending: "待执行",
  in_progress: "进行中",
  completed: "已完成",
  skipped: "无搜索结果",
  interrupted: "已中断",
  failed: "失败"
};

function formatTaskStatus(status: string): string {
  return TASK_STATUS_LABEL[status] ?? status;
}

const totalTasks = computed(() => todoTasks.value.length);
const completedTasks = computed(() =>
  todoTasks.value.filter((task) => task.status === "completed").length
);

const workflowStatus = computed(() => {
  if (loading.value) return "研究进行中";
  if (selectedRun.value?.status==='paused') return "研究已暂停";
  if (selectedRun.value?.status === "interrupted") return "研究已中断";
  if (error.value) return "研究失败";
  if (todoTasks.value.some(task => ["failed","skipped","paused","interrupted"].includes(task.status))) {
    return completedTasks.value ? "研究结束，部分任务未完成" : "未获得有效资料";
  }
  return "研究流程完成";
});

const currentTask = computed(() => {
  if (activeTaskId.value !== null) {
    return todoTasks.value.find((task) => task.id === activeTaskId.value) ?? null;
  }
  return leftTasks.value[0] ?? null;
});

const pulse = (flag: typeof summaryHighlight) => {
  flag.value = false;
  requestAnimationFrame(() => {
    flag.value = true;
    window.setTimeout(() => {
      flag.value = false;
    }, 1200);
  });
};

function parseSources(raw: string): SourceItem[] {
  if (!raw) {
    return [];
  }

  const items: SourceItem[] = [];
  const lines = raw.split("\n");

  let current: SourceItem | null = null;
  const truncate = (value: string, max = 360) => {
    const trimmed = value.trim();
    return trimmed.length > max ? `${trimmed.slice(0, max)}…` : trimmed;
  };

  const flush = () => {
    if (!current) {
      return;
    }
    const normalized: SourceItem = {
      title: current.title?.trim() || "",
      url: current.url?.trim() || "",
      snippet: current.snippet ? truncate(current.snippet) : "",
      raw: current.raw ? truncate(current.raw, 420) : ""
    };

    if (
      normalized.title ||
      normalized.url ||
      normalized.snippet ||
      normalized.raw
    ) {
      if (!normalized.title && normalized.url) {
        normalized.title = normalized.url;
      }
      items.push(normalized);
    }
    current = null;
  };

  const ensureCurrent = () => {
    if (!current) {
      current = { title: "", url: "", snippet: "", raw: "" };
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    if (/^\*/.test(trimmed) && trimmed.includes(" : ")) {
      flush();
      const withoutBullet = trimmed.replace(/^\*\s*/, "");
      const [titlePart, urlPart] = withoutBullet.split(" : ");
      current = {
        title: titlePart?.trim() || "",
        url: urlPart?.trim() || "",
        snippet: "",
        raw: ""
      };
      continue;
    }

    if (/^(Source|信息来源)\s*:/.test(trimmed)) {
      flush();
      const [, titlePart = ""] = trimmed.split(/:\s*(.+)/);
      current = {
        title: titlePart.trim(),
        url: "",
        snippet: "",
        raw: ""
      };
      continue;
    }

    if (/^URL\s*:/.test(trimmed)) {
      ensureCurrent();
      const [, urlPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.url = urlPart.trim();
      continue;
    }

    if (
      /^(Most relevant content from source|信息内容)\s*:/.test(trimmed)
    ) {
      ensureCurrent();
      const [, contentPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.snippet = contentPart.trim();
      continue;
    }

    if (
      /^(Full source content limited to|信息内容限制为)\s*:/.test(trimmed)
    ) {
      ensureCurrent();
      const [, rawPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.raw = rawPart.trim();
      continue;
    }

    if (/^https?:\/\//.test(trimmed)) {
      ensureCurrent();
      if (!current!.url) {
        current!.url = trimmed;
        continue;
      }
    }

    ensureCurrent();
    current!.raw = current!.raw ? `${current!.raw}\n${trimmed}` : trimmed;
  }

  flush();
  return items;
}

function extractOptionalString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function ensureRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function applyNoteMetadata(
  task: TodoTaskView,
  payload: Record<string, unknown>
): void {
  const noteId = extractOptionalString(payload.note_id);
  if (noteId) {
    task.noteId = noteId;
  }
  const notePath = extractOptionalString(payload.note_path);
  if (notePath) {
    task.notePath = notePath;
  }
}

async function copyNotePath(path: string | null | undefined) {
  if (!path) {
    return;
  }

  try {
    await navigator.clipboard.writeText(path);
    progressLogs.value.push(`已复制笔记路径：${path}`);
  } catch (error) {
    console.warn("无法直接复制到剪贴板", error);
    window.prompt("复制以下笔记路径", path);
    progressLogs.value.push("请手动复制笔记路径");
  }
}

function resetWorkflowState() {
  for(const key of Object.keys(taskDetailViews))delete taskDetailViews[Number(key)];
  todoTasks.value = [];
  activeTaskId.value = null;
  reportMarkdown.value = "";
  reportStale.value=false;
  reportSelected.value = false;
  progressLogs.value = [];
  summaryHighlight.value = false;
  sourcesHighlight.value = false;
  reportHighlight.value = false;
  toolHighlight.value = false;
  logsCollapsed.value = false;
}

function findTask(taskId: unknown): TodoTaskView | undefined {
  const numeric =
    typeof taskId === "number"
      ? taskId
      : typeof taskId === "string"
      ? Number(taskId)
      : NaN;
  if (Number.isNaN(numeric)) {
    return undefined;
  }
  return todoTasks.value.find((task) => task.id === numeric);
}

function upsertTaskMetadata(task: TodoTaskView, payload: Record<string, unknown>) {
  if (typeof payload.title === "string" && payload.title.trim()) {
    task.title = payload.title.trim();
  }
  if (typeof payload.intent === "string" && payload.intent.trim()) {
    task.intent = payload.intent.trim();
  }
  if (typeof payload.query === "string" && payload.query.trim()) {
    task.query = payload.query.trim();
  }
}

function handleResearchEvent(event: ResearchStreamEvent) {

        if (event.type === 'reset') { resetWorkflowState();return; }
        if(event.type==='task_retry_queued'){const task=findTask(event.task_id);if(task)task.retryQueued=true;return;}
        if(event.type==='task_retry_queue_cleared'){for(const task of todoTasks.value)task.retryQueued=false;return;}
        if (event.type === 'tasks_updated') {
          const changed=new Set(Array.isArray(event.changed_ids)?event.changed_ids:[]);
          for(const task of todoTasks.value)if(changed.has(task.id)){task.summary='';task.sourcesSummary='';task.sourceItems=[];task.notices=[];task.toolCalls=[];task.noteId=null;task.notePath=null;task.retryQueued=false;}
          reportStale.value=true;error.value='';
          handleResearchEvent({...event,type:'todo_list'});
          return;
        }
        if (event.type === "status") {
          const message =
            typeof event.message === "string" && event.message.trim()
              ? event.message
              : "流程状态更新";
          progressLogs.value.push(message);

          const payload = event as Record<string, unknown>;
          const task = findTask(payload.task_id);
          if (task && message) {
            task.notices.push(message);
            applyNoteMetadata(task, payload);
          }
          return;
        }

        if (event.type === "todo_list") {
          const tasks = Array.isArray(event.tasks)
            ? (event.tasks as Record<string, unknown>[])
            : [];

          todoTasks.value = tasks.map((item, index) => {
            const rawId =
              typeof item.id === "number"
                ? item.id
                : typeof item.id === "string"
                ? Number(item.id)
                : index + 1;
            const id = Number.isFinite(rawId) ? Number(rawId) : index + 1;
            const noteId =
              typeof item.note_id === "string" && item.note_id.trim()
                ? item.note_id.trim()
                : null;
            const notePath =
              typeof item.note_path === "string" && item.note_path.trim()
                ? item.note_path.trim()
                : null;

            const existing=findTask(id);
            const values={
              id,
              title:
                typeof item.title === "string" && item.title.trim()
                  ? item.title.trim()
                  : `任务${id}`,
              intent:
                typeof item.intent === "string" && item.intent.trim()
                  ? item.intent.trim()
                  : "探索与主题相关的关键信息",
              query:
                typeof item.query === "string" && item.query.trim()
                  ? item.query.trim()
                  : form.topic.trim(),
              status:
                typeof item.status === "string" && item.status.trim()
                  ? item.status.trim()
                  : "pending",
              summary: typeof item.summary==='string'?item.summary:'',
              sourcesSummary: typeof item.sources_summary==='string'?item.sources_summary:'',
              sourceItems: typeof item.sources_summary==='string'?parseSources(item.sources_summary):[],
              notices: existing?.notices || [],
              noteId,
              notePath,
              toolCalls: existing?.toolCalls || []
            } as TodoTaskView;
            return existing?Object.assign(existing,values):values;
          });

          if (todoTasks.value.length) {
            if(!todoTasks.value.some(t=>t.id===activeTaskId.value))activeTaskId.value = todoTasks.value[0].id;
            progressLogs.value.push("已生成任务清单");
          } else {
            progressLogs.value.push("未生成任务清单，使用默认任务继续");
          }
          return;
        }

        if (event.type === "task_status") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }

          upsertTaskMetadata(task, payload);
          applyNoteMetadata(task, payload);
          const status =
            typeof event.status === "string" && event.status.trim()
              ? event.status.trim()
              : task.status;
          task.status = status;

          if (status === "in_progress") {
            task.summary = "";
            task.sourcesSummary = "";
            task.sourceItems = [];
            task.notices = [];
            if (activeTaskId.value === null) activeTaskId.value = task.id;
            progressLogs.value.push(`开始执行任务：${task.title}`);
          } else if (status === "completed") {
            if (typeof event.summary === "string" && event.summary.trim()) {
              task.summary = event.summary.trim();
            }
            if (
              typeof event.sources_summary === "string" &&
              event.sources_summary.trim()
            ) {
              task.sourcesSummary = event.sources_summary.trim();
              task.sourceItems = parseSources(task.sourcesSummary);
            }
            progressLogs.value.push(`完成任务：${task.title}`);
            if (activeTaskId.value === task.id) {
              pulse(summaryHighlight);
              pulse(sourcesHighlight);
            }
          } else if (status === "failed" || status === "skipped") {
            const detail = extractOptionalString(payload.detail) ||
              (status === "failed" ? "任务执行失败，请查看后端日志。" : "搜索正常结束，但没有结果。");
            if (!task.notices.includes(detail)) task.notices.push(detail);
            progressLogs.value.push(`${status === "failed" ? "任务失败" : "任务跳过"}：${task.title}。${detail}`);
          }
          return;
        }

        if (event.type === "sources") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }

          const textCandidates = [
            payload.latest_sources,
            payload.sources_summary,
            payload.raw_context
          ];
          const latestText = textCandidates
            .map((value) => (typeof value === "string" ? value.trim() : ""))
            .find((value) => value);

          if (latestText) {
            task.sourcesSummary = latestText;
            task.sourceItems = parseSources(latestText);
            if (activeTaskId.value === task.id) {
              pulse(sourcesHighlight);
            }
            progressLogs.value.push(`已更新任务来源：${task.title}`);
          }

          if (typeof payload.backend === "string") {
            progressLogs.value.push(
              `当前使用搜索后端：${payload.backend}`
            );
          }

          applyNoteMetadata(task, payload);

          return;
        }

        if (event.type === "task_summary_chunk") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }
          const chunk =
            typeof event.content === "string" ? event.content : "";
          task.summary += chunk;
          applyNoteMetadata(task, payload);
          if (activeTaskId.value === task.id) {
            pulse(summaryHighlight);
          }
          return;
        }

        if (event.type === "tool_call") {
          const payload = event as Record<string, unknown>;
          const eventId =
            typeof payload.event_id === "number"
              ? payload.event_id
              : Date.now();
          const agent =
            typeof payload.agent === "string" && payload.agent.trim()
              ? payload.agent.trim()
              : "Agent";
          const tool =
            typeof payload.tool === "string" && payload.tool.trim()
              ? payload.tool.trim()
              : "tool";
          const parameters = ensureRecord(payload.parameters);
          const result =
            typeof payload.result === "string" ? payload.result : "";
          const noteId = extractOptionalString(payload.note_id);
          const notePath = extractOptionalString(payload.note_path);

          const task = findTask(payload.task_id);
          if (task) {
            task.toolCalls.push({
              eventId,
              agent,
              tool,
              parameters,
              result,
              noteId,
              notePath,
              timestamp: Date.now()
            });
            if (noteId) {
              task.noteId = noteId;
            }
            if (notePath) {
              task.notePath = notePath;
            }
            const logSummary = noteId
              ? `${agent} 调用了 ${tool}（任务 ${task.id}，笔记 ${noteId}）`
              : `${agent} 调用了 ${tool}（任务 ${task.id}）`;
            progressLogs.value.push(logSummary);
            if (activeTaskId.value === task.id) {
              pulse(toolHighlight);
            }
          } else {
            progressLogs.value.push(`${agent} 调用了 ${tool}`);
          }
          return;
        }

        if (event.type === "final_report") {
          const report =
            typeof event.report === "string" && event.report.trim()
              ? event.report.trim()
              : "";
          reportMarkdown.value = publicAnswer(report, "report");
          reportStale.value=false;
          pulse(reportHighlight);
          progressLogs.value.push("最终报告已生成");
          return;
        }

        if (event.type === "error") {
          const detail =
            typeof event.detail === "string" && event.detail.trim()
              ? event.detail
              : "研究过程中发生错误";
          error.value = detail;
          progressLogs.value.push("研究失败，已停止流程");
        }

}
type WorkspaceNote={key:string;note:PersonalNote};
const personalNotes=ref<PersonalNote[]>([]);const workspaceNotes=ref<WorkspaceNote[]>([]);
const activeLeftNote=ref('');const noteActive=ref(false);
const noteEditors=shallowReactive(new Map<string,InstanceType<typeof NoteEditor>>());
function setNoteEditor(key:string,editor:unknown){if(editor)noteEditors.set(key,editor as InstanceType<typeof NoteEditor>);else noteEditors.delete(key);}
async function loadNotes(){try{personalNotes.value=await api<PersonalNote[]>('/notes');}catch{historyError.value='笔记列表加载失败';}}
function activateLeftNote(key:string){activeLeftNote.value=key;noteActive.value=true;resetContentScroll();}
function removeNote(key:string){workspaceNotes.value=workspaceNotes.value.filter(n=>n.key!==key);rightDocuments.value=rightDocuments.value.filter(k=>k!==key);if(activeLeftNote.value===key){activeLeftNote.value='';noteActive.value=false;}reconcileDocuments();}
function requestCloseNote(key=activeLeftNote.value){if(noteEditors.get(key)?.allowClose()!==false)removeNote(key);}
function createNote(side:'left'|'right'='left'){const key='note:'+crypto.randomUUID();workspaceNotes.value.push({key,note:{title:form.topic+' · 笔记',html:marked.parse(reportMarkdown.value,{async:false}) as string,run_id:selectedRun.value?.id}});if(side==='right'){rightDocuments.value.push(key);activateRight(key);}else activateLeftNote(key);}
async function ensureNote(note:PersonalNote){const existing=workspaceNotes.value.find(n=>n.note.id && n.note.id===note.id);if(existing)return existing.key;const epoch=comparisonEpoch;const full=await api<PersonalNote>('/notes/'+note.id);if(epoch!==comparisonEpoch)return null;const key='note:'+note.id;if(!workspaceNotes.value.some(n=>n.key===key))workspaceNotes.value.push({key,note:full});return key;}
async function openNote(note:PersonalNote){try{const key=await ensureNote(note);if(!key)return;if(isOnRight(key))activateRight(key);else activateLeftNote(key);}catch{historyError.value='笔记打开失败';}}
async function noteSaved(key:string){removeNote(key);await loadNotes();}
onMounted(()=>{void loadNotes()});

type DragDocument={kind:'report'|'task'|'note'|'key';id?:number;note?:PersonalNote;key?:string};
const rightDocuments=ref<string[]>([]);const activeRightKey=ref('');
const comparisonError=ref('');const dragDocument=ref<DragDocument|null>(null);let comparisonEpoch=0;
const leftTasks=computed(()=>todoTasks.value.filter(t=>!isOnRight('task:'+t.id)));
const leftNotes=computed(()=>workspaceNotes.value.filter(n=>!isOnRight(n.key)));
function isOnRight(key:string){return rightDocuments.value.includes(key);}
function documentTask(key:string){return todoTasks.value.find(t=>'task:'+t.id===key);}
function documentTitle(key:string){return key==='report'?'最终报告':key.startsWith('note:')?'Note · '+(workspaceNotes.value.find(n=>n.key===key)?.note.title||'笔记'):documentTask(key)?.title||'子任务报告';}
const comparison=computed(()=>{const key=activeRightKey.value;if(!rightDocuments.value.includes(key))return null;return {kind:key==='report'?'report':key.startsWith('note:')?'note':'task',id:key.startsWith('task:')?Number(key.slice(5)):undefined};});
const comparisonTask=computed(()=>documentTask(activeRightKey.value));
const documentPanes=ref<HTMLElement|null>(null);const paneWidth=ref(800);const splitPercent=ref(50);
const splitWidth=computed(()=>Math.max(280,Math.min(paneWidth.value-290,(paneWidth.value-10)*splitPercent.value/100)));
function setSplitWidth(value:number){splitPercent.value=value/(paneWidth.value-10)*100;}
let paneObserver:ResizeObserver|undefined;
watch(documentPanes,element=>{paneObserver?.disconnect();if(element){paneObserver=new ResizeObserver(()=>{paneWidth.value=element.clientWidth;});paneObserver.observe(element);}}, {flush:'post'});
onBeforeUnmount(()=>paneObserver?.disconnect());
function activateRight(key:string){const changed=activeRightKey.value!==key;activeRightKey.value=key;void nextTick(()=>{const pane=documentPanes.value?.querySelector<HTMLElement>('.comparison-pane');if(changed && pane)pane.scrollTop=0;pane?.querySelector<HTMLElement>('[role=tab][aria-selected=true]')?.scrollIntoView({block:'nearest',inline:'nearest'});});}
function activateDocument(key:string){if(isOnRight(key)){activateRight(key);return;}if(key==='report')selectReport();else if(key.startsWith('task:'))selectTask(Number(key.slice(5)));else activateLeftNote(key);}
function taskVisible(id:number){return (!noteActive.value&&!reportSelected.value&&activeTaskId.value===id)||activeRightKey.value==='task:'+id;}
function reconcileDocuments(){
 const keys=[...(reportReady.value?['report']:[]),...todoTasks.value.map(t=>'task:'+t.id),...workspaceNotes.value.map(n=>n.key)];
 rightDocuments.value=rightDocuments.value.filter(k=>keys.includes(k));
 if(!rightDocuments.value.includes(activeRightKey.value))activeRightKey.value=rightDocuments.value[0]||'';
 const left=keys.filter(k=>!isOnRight(k));const current=noteActive.value?activeLeftNote.value:reportSelected.value?'report':'task:'+activeTaskId.value;
 if(!left.includes(current)){noteActive.value=false;reportSelected.value=false;activeTaskId.value=null;if(left.length)activateDocument(left[0]);}
}
watch(()=>[reportReady.value,...todoTasks.value.map(t=>t.id)],reconcileDocuments);
function beginDocumentDrag(event:DragEvent,doc:DragDocument){if(editingTasks.value){event.preventDefault();return;}dragDocument.value=doc;comparisonError.value='';event.dataTransfer?.setData('application/x-research-document',doc.kind);if(event.dataTransfer)event.dataTransfer.effectAllowed='move';}
function startNoteDrag(payload:{event:DragEvent;note:PersonalNote}){beginDocumentDrag(payload.event,{kind:'note',note:payload.note});}
function endDocumentDrag(){dragDocument.value=null;}
function closeComparison(){const active=activeRightKey.value;rightDocuments.value=[];activeRightKey.value='';if(active)activateDocument(active);reconcileDocuments();}
function closeDocumentsForNavigation(){for(const editor of noteEditors.values())if(editor.allowClose()===false)return false;comparisonEpoch++;workspaceNotes.value=[];activeLeftNote.value='';noteActive.value=false;rightDocuments.value=[];activeRightKey.value='';endDocumentDrag();return true;}
async function dropDocument(side:'left'|'right'){
 const doc=dragDocument.value;endDocumentDrag();if(!doc||editingTasks.value)return;
 const epoch=comparisonEpoch;
 try{
 const key=doc.kind==='note'&&doc.note?await ensureNote(doc.note):doc.kind==='key'?doc.key:doc.kind==='report'?'report':'task:'+doc.id;
 if(!key||epoch!==comparisonEpoch)return;
 if(side==='right'){if(!isOnRight(key))rightDocuments.value.push(key);activateRight(key);}else{rightDocuments.value=rightDocuments.value.filter(k=>k!==key);activateDocument(key);}
 reconcileDocuments();comparisonError.value='';
 }catch{if(epoch===comparisonEpoch)comparisonError.value='文档加载失败，请重试';}
}

const homeMode=ref<'research'|'chat'>('research');
const chatContext=ref<ChatContext|null>(null);
const chatPanel=ref<InstanceType<typeof ChatPanel>|null>(null);
async function openHomeChat(){if(!closeDocumentsForNavigation())return;homeMode.value='chat';openChat();await nextTick();chatPanel.value?.newConversation();}
function openChat(context?:ChatContext){void loadProfiles();chatContext.value=context?{...context,document:'assistant'}:{runId:selectedRun.value?.id||'',document:'assistant',scope:'research',revision:selectedRun.value?.revision||0,quote:''};}
// Keep user widths, adapting them to the available desktop viewport.
const viewportWidth=ref(window.innerWidth);
const preferredWidths=reactive({sidebar:280,tasks:250,chat:350});
try{const saved=JSON.parse(localStorage.getItem('research-column-widths')||'null');if(saved)for(const key of ['sidebar','tasks','chat'] as const)if(Number.isFinite(saved[key]))preferredWidths[key]=Math.max(210,Math.min(700,saved[key]));}catch{}
const columnSizes=computed(()=>{const size={...preferredWidths,tasks:preferredWidths.tasks+(editingTasks.value?50:0)};const minimum={sidebar:230,tasks:210,chat:300};const total=Math.max(viewportWidth.value,chatContext.value?1220:900);let excess=size.sidebar+size.tasks+(chatContext.value?size.chat:0)+450-total;for(const key of ['sidebar','tasks','chat'] as const){if(key==='chat'&&!chatContext.value)continue;const cut=Math.min(Math.max(0,excess),Math.max(0,size[key]-minimum[key]));size[key]-=cut;excess-=cut;}return size;});
const columnRoom=computed(()=>Math.max(0,Math.max(viewportWidth.value,chatContext.value?1220:900)-450-columnSizes.value.sidebar-columnSizes.value.tasks-(chatContext.value?columnSizes.value.chat:0)));
const layoutWidths=computed(()=>({'--sidebar-width':columnSizes.value.sidebar+'px','--tasks-width':columnSizes.value.tasks+'px','--chat-width':columnSizes.value.chat+'px',minWidth:(chatContext.value?1220:900)+'px'}));
function resizeColumn(key:'sidebar'|'tasks'|'chat',width:number){preferredWidths[key]=width-(key==='tasks'&&editingTasks.value?50:0);try{localStorage.setItem('research-column-widths',JSON.stringify(preferredWidths));}catch{}}
function resizeViewport(){viewportWidth.value=window.innerWidth;}
onMounted(()=>window.addEventListener('resize',resizeViewport));onBeforeUnmount(()=>window.removeEventListener('resize',resizeViewport));
const editingTasks=ref(false);const actionBusy=ref(false);
async function runAction(path:string,method='POST',body?:unknown){
  if(!selectedRun.value||actionBusy.value)return;if(!closeDocumentsForNavigation())return;
  const id=selectedRun.value.id;const epoch=++selectionEpoch;actionBusy.value=true;
  try{await api(`/research-runs/${id}/${path}`,{method,body:body?JSON.stringify(body):undefined});if(epoch!==selectionEpoch)return;
    editingTasks.value=false;error.value='';
    if(path==='topic')await openRun(id,false);
    else{const detail=await api<RunDetail>(`/research-runs/${id}?after=${cursor}`);if(epoch===selectionEpoch)applyDetail(detail);}
    await refreshHistory();
  }catch(e){if(epoch===selectionEpoch)error.value=e instanceof Error?e.message:'操作失败';}finally{actionBusy.value=false;}
}
function retryable(task:TodoTaskView){return ['failed','paused','interrupted','skipped'].includes(task.status);}
function retryTask(task:TodoTaskView){void runAction(`tasks/${task.id}/retry`);}
function controlResearch(){void runAction(selectedRun.value?.status==='running'?'pause':'resume');}
function saveTasks(tasks:{id?:number;title:string;intent:string}[]){const before=todoTasks.value.map(({id,title,intent})=>({id,title,intent}));if(JSON.stringify(before)===JSON.stringify(tasks)){editingTasks.value=false;return}void runAction('tasks','PUT',{tasks});}
const topicDialog=ref<HTMLDialogElement|null>(null);const topicDraft=ref('');
function editTopic(){topicDraft.value=form.topic;topicDialog.value?.showModal();}
function saveTopic(){const topic=topicDraft.value.trim();if(!topic)return;topicDialog.value?.close();if(topic!==form.topic)void runAction('topic','PUT',{topic});}
const historyRuns=ref<ResearchRun[]>([]);
const selectedRun=ref<ResearchRun|null>(null);
const historyError=ref('');const submitting=ref(false);
let selectionEpoch=0;let cursor=0;let polling=false;let pollTimer:ReturnType<typeof setInterval>|undefined;
async function refreshHistory(){try{historyRuns.value=await api<ResearchRun[]>('/research-runs');historyError.value='';}catch(e){historyError.value=e instanceof Error?e.message:'历史记录加载失败';}}
function runHash(id?:string){window.history.pushState(null,'',id?`#research/${id}`:window.location.pathname);}
async function openRun(id:string,navigate=true){
  if(!closeDocumentsForNavigation()){if(!navigate)runHash(selectedRun.value?.id);return;}editingTasks.value=false;
  if(chatContext.value)chatContext.value={...chatContext.value,runId:id,scope:'research',revision:0,quote:''};selectionEpoch++;cursor=0;resetWorkflowState();error.value='';selectedRun.value=null;loading.value=true;isExpanded.value=true;
  if(navigate)runHash(id);
  const epoch=selectionEpoch;
  try{const d=await api<RunDetail>(`/research-runs/${id}`);if(epoch!==selectionEpoch)return;applyDetail(d);}
  catch(e){if(epoch!==selectionEpoch)return;loading.value=false;error.value=e instanceof Error?e.message:'记录加载失败';}
}
function applyDetail(d:RunDetail){
  // Apply the default only on entry or lifecycle changes, preserving manual toggles during polling.
  const previous = selectedRun.value;
  const lifecycleChanged = previous?.id !== d.record.id || previous?.status !== d.record.status;
  if(previous && previous.id===d.record.id && previous.topic!==d.record.topic && cursor>0) { void openRun(d.record.id,false);return; }
  selectedRun.value=d.record;form.topic=d.record.topic;form.searchApi=d.record.search_api;
  if(chatContext.value && chatContext.value.revision!==(d.record.revision||0))chatContext.value={...chatContext.value,revision:d.record.revision||0};
  for(const item of d.events)handleResearchEvent(item.event);
  reconcileDocuments();
  if(lifecycleChanged) logsCollapsed.value=d.record.status!=='running';
  cursor=d.next_cursor;loading.value=d.record.status==='running';
  if(!loading.value)for(const task of todoTasks.value)task.retryQueued=false;
  error.value=d.record.error||'';
  if(d.record.status==='paused')for(const task of todoTasks.value)if(['pending','in_progress'].includes(task.status))task.status='paused';
  if(d.record.status==='interrupted')for(const task of todoTasks.value)if(['pending','in_progress'].includes(task.status))task.status='interrupted';
}
async function poll(){
  if(polling)return;polling=true;
  const id=selectedRun.value?.id;const epoch=selectionEpoch;
  try{
    if(id && isExpanded.value){const d=await api<RunDetail>(`/research-runs/${id}?after=${cursor}`);if(epoch===selectionEpoch){applyDetail(d);historyError.value='';}}
    await refreshHistory();
  }catch(e){historyError.value=e instanceof Error?e.message:'连接暂时中断，正在重连；研究仍在后台执行';}
  finally{polling=false;}
}
const handleSubmit=async()=>{
  if(submitting.value)return;
  if(!form.topic.trim()||!form.modelProfileId){error.value='请输入主题并选择研究模型';return;}
  submitting.value=true;error.value='';
  try{const r=await api<ResearchRun>('/research-runs',{method:'POST',body:JSON.stringify({topic:form.topic.trim(),search_api:form.searchApi||undefined,model_profile_id:form.modelProfileId,document_ids: selectedDocumentIds.value})});await openRun(r.id);await refreshHistory();}
  catch(e){error.value=e instanceof Error?e.message:'启动研究失败';}
  finally{submitting.value=false;}
};
const goBack=()=>{if(!closeDocumentsForNavigation())return false;if(chatContext.value)chatContext.value={...chatContext.value,runId:'',scope:'research',revision:0,quote:''};editingTasks.value=false;selectionEpoch++;selectedRun.value=null;isExpanded.value=false;loading.value=false;error.value='';runHash();return true;};
const startNewResearch=()=>{if(!goBack())return;homeMode.value='research';resetWorkflowState();form.topic='';};
async function renameRun(r:ResearchRun){const title=window.prompt('修改研究标题',r.title);if(!title?.trim()||title===r.title)return;try{await api(`/research-runs/${r.id}`,{method:'PATCH',body:JSON.stringify({title:title.trim()})});await refreshHistory();}catch(e){historyError.value=e instanceof Error?e.message:'重命名失败';}}
async function deleteRun(r:ResearchRun){if(!window.confirm('删除这条研究历史及页面记录？此操作不可撤销。'))return;try{await api(`/research-runs/${r.id}`,{method:'DELETE'});if(selectedRun.value?.id===r.id)startNewResearch();await refreshHistory();}catch(e){historyError.value=e instanceof Error?e.message:'删除失败';}}
function restoreRoute(){const match=location.hash.match(/^#research\/([a-zA-Z0-9_-]+)$/);if(match)void openRun(match[1],false);else {if(!closeDocumentsForNavigation()){runHash(selectedRun.value?.id);return;}if(chatContext.value)chatContext.value={...chatContext.value,runId:'',scope:'research',revision:0,quote:''};selectionEpoch++;isExpanded.value=false;selectedRun.value=null;loading.value=false;}}
onMounted(async()=>{await refreshHistory();restoreRoute();pollTimer=setInterval(poll,1000);window.addEventListener('popstate',restoreRoute);});
onBeforeUnmount(()=>{selectionEpoch++;if(pollTimer)clearInterval(pollTimer);window.removeEventListener('popstate',restoreRoute);});
</script>


<style scoped>
.app-shell {
  position: relative;
  min-height: 100vh;
  padding: 72px 24px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: radial-gradient(circle at 20% 20%, #f8fafc, #dbeafe 60%);
  color: #1f2937;
  overflow: hidden;
  box-sizing: border-box;
  transition: padding 0.4s ease;
}

.app-shell.expanded {
  padding: 0;
  align-items: stretch;
}

.aurora {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.55;
}

.aurora span {
  position: absolute;
  width: 45vw;
  height: 45vw;
  max-width: 520px;
  max-height: 520px;
  background: radial-gradient(circle, rgba(148, 197, 255, 0.35), transparent 60%);
  filter: blur(90px);
  animation: float 26s infinite linear;
}

.aurora span:nth-child(1) {
  top: -20%;
  left: -18%;
  animation-delay: 0s;
}

.aurora span:nth-child(2) {
  bottom: -25%;
  right: -20%;
  background: radial-gradient(circle, rgba(166, 139, 255, 0.28), transparent 60%);
  animation-delay: -9s;
}

.aurora span:nth-child(3) {
  top: 35%;
  left: 45%;
  background: radial-gradient(circle, rgba(164, 219, 216, 0.26), transparent 60%);
  animation-delay: -16s;
}

.layout {
  position: relative;
  width: 100%;
  display: flex;
  gap: 24px;
  z-index: 1;
  transition: all 0.4s ease;
}

.layout-centered {
  max-width: 600px;
  justify-content: center;
  align-items: center;
}

.layout-fullscreen {
  height: 100vh;
  max-width: 100%;
  gap: 0;
  align-items: stretch;
}

.panel {
  position: relative;
  flex: 1 1 360px;
  padding: 24px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(8px);
  overflow: hidden;
}

.panel-form {
  max-width: 420px;
}

.panel-centered {
  width: 100%;
  max-width: 600px;
  padding: 40px;
  box-shadow: 0 32px 64px rgba(15, 23, 42, 0.15);
  transform: scale(1);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.panel-centered:hover {
  transform: scale(1.02);
  box-shadow: 0 40px 80px rgba(15, 23, 42, 0.2);
}

.panel-result {
  min-width: 360px;
  flex: 2 1 420px;
}

.panel::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(125, 86, 255, 0.1));
  opacity: 0;
  transition: opacity 0.35s ease;
  z-index: 0;
}

.panel:hover::before {
  opacity: 1;
}

.panel > * {
  position: relative;
  z-index: 1;
}

.panel-form h1 {
  margin: 0;
  font-size: 26px;
  letter-spacing: 0.01em;
}

.panel-form p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.logo {
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  border-radius: 16px;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  box-shadow: 0 12px 28px rgba(59, 130, 246, 0.4);
}

.logo svg {
  width: 28px;
  height: 28px;
  fill: #f8fafc;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field span {
  font-weight: 600;
  color: #475569;
}

textarea,
input,
select {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(255, 255, 255, 0.92);
  color: #1f2937;
  font-size: 14px;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

textarea:focus,
input:focus,
select:focus {
  outline: none;
  border-color: rgba(37, 99, 235, 0.65);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
  background: #ffffff;
}

.options {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.option {
  flex: 1;
  min-width: 140px;
}

.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.submit {
  align-self: flex-start;
  padding: 12px 24px;
  border-radius: 16px;
  border: none;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #ffffff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s, opacity 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  position: relative;
}

.submit-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.submit .spinner {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: rgba(255, 255, 255, 0.85);
  stroke-linecap: round;
  animation: spin 1s linear infinite;
}

.submit:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.submit:not(:disabled):hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.28);
}

.secondary-btn {
  padding: 10px 18px;
  border-radius: 14px;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.28);
  color: #1f2937;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.secondary-btn:hover {
  background: rgba(148, 163, 184, 0.2);
  border-color: rgba(148, 163, 184, 0.35);
  color: #0f172a;
}

.error-chip {
  margin-top: 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(248, 113, 113, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.35);
  border-radius: 14px;
  color: #b91c1c;
  font-size: 14px;
}

.error-chip svg {
  width: 18px;
  height: 18px;
  fill: currentColor;
}

.panel-result {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.status-main {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.status-controls {
  display: flex;
  gap: 8px;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(191, 219, 254, 0.28);
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  color: #1f2937;
  border: 1px solid rgba(59, 130, 246, 0.35);
  transition: background 0.3s ease, color 0.3s ease;
}

.status-chip.active {
  background: rgba(129, 140, 248, 0.2);
  border-color: rgba(129, 140, 248, 0.4);
  color: #1e293b;
}

.status-chip .dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #2563eb;
  box-shadow: 0 0 12px rgba(37, 99, 235, 0.45);
  animation: pulse 1.8s ease-in-out infinite;
}

.status-meta {
  color: #64748b;
  font-size: 13px;
}

.timeline-wrapper {
  margin-top: 12px;
  max-height: 220px;
  overflow-y: auto;
  padding-right: 8px;
  scrollbar-width: thin;
  scrollbar-color: rgba(129, 140, 248, 0.45) rgba(226, 232, 240, 0.6);
}

.timeline-wrapper::-webkit-scrollbar {
  width: 6px;
}

.timeline-wrapper::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.6);
  border-radius: 999px;
}

.timeline-wrapper::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(129, 140, 248, 0.8), rgba(59, 130, 246, 0.7));
  border-radius: 999px;
}

.timeline-wrapper::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.9), rgba(37, 99, 235, 0.8));
}

.timeline {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: relative;
  padding-left: 12px;
}

.timeline::before {
  content: "";
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 0;
  width: 2px;
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.35), rgba(129, 140, 248, 0.15));
}

.timeline li {
  position: relative;
  padding-left: 24px;
  color: #1e293b;
  font-size: 14px;
  line-height: 1.5;
}

.timeline-node {
  position: absolute;
  left: -12px;
  top: 6px;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, #38bdf8, #7c3aed);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.22);
}

.timeline-enter-active,
.timeline-leave-active {
  transition: all 0.35s ease, opacity 0.35s ease;
}

.timeline-enter-from,
.timeline-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.tasks-section {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 20px;
  align-items: start;
}

@media (max-width: 960px) {
  .tasks-section {
    grid-template-columns: 1fr;
  }
}

.tasks-list {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 18px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.4);
}

.tasks-list h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.tasks-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-item {
  border-radius: 14px;
  border: 1px solid transparent;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.task-item.completed {
  border-color: rgba(56, 189, 248, 0.35);
  background: rgba(191, 219, 254, 0.28);
}

.task-item.active {
  border-color: rgba(129, 140, 248, 0.5);
  background: rgba(224, 231, 255, 0.5);
}

.task-button {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px 6px;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.task-title {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
}

.task-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  color: #1f2937;
  background: rgba(148, 163, 184, 0.2);
}

.task-status.pending {
  background: rgba(148, 163, 184, 0.18);
  color: #475569;
}

.task-status.in_progress {
  background: rgba(129, 140, 248, 0.24);
  color: #312e81;
}

.task-status.completed {
  background: rgba(34, 197, 94, 0.2);
  color: #15803d;
}

.task-status.failed,
.task-status.skipped {
  background: rgba(248, 113, 113, 0.18);
  color: #b91c1c;
}

.task-intent {
  margin: 0;
  padding: 0 14px 12px 14px;
  font-size: 13px;
  color: #64748b;
}

.task-detail {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 18px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.5);
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
}

.task-chip-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.task-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.task-header .muted {
  margin: 6px 0 0;
}

.task-label {
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(191, 219, 254, 0.32);
  border: 1px solid rgba(59, 130, 246, 0.35);
  font-size: 12px;
  color: #1e3a8a;
}

.task-label.note-chip {
  background: rgba(34, 197, 94, 0.2);
  border-color: rgba(34, 197, 94, 0.35);
  color: #15803d;
}

.task-label.path-chip {
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

.path-label {
  font-weight: 500;
}

.path-text {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-action {
  border: none;
  background: rgba(56, 189, 248, 0.2);
  color: #0369a1;
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.chip-action:hover {
  background: rgba(14, 165, 233, 0.28);
  color: #0f172a;
}

.task-notices {
  background: rgba(191, 219, 254, 0.28);
  border: 1px solid rgba(96, 165, 250, 0.35);
  border-radius: 16px;
  padding: 14px 18px;
  color: #1f2937;
}

.task-notices h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.task-notices ul {
  list-style: disc;
  margin: 0 0 0 18px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-notices li {
  font-size: 13px;
}

.report-block {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 18px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.report-block h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.block-pre {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular,
    Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1f2937;
  background: rgba(248, 250, 252, 0.9);
  padding: 16px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  overflow: auto;
  max-height: 420px;
  scrollbar-width: thin;
  scrollbar-color: rgba(129, 140, 248, 0.6) rgba(226, 232, 240, 0.7);
}

.block-pre::-webkit-scrollbar {
  width: 6px;
}

.block-pre::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.7);
  border-radius: 999px;
}

.block-pre::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.75), rgba(59, 130, 246, 0.65));
  border-radius: 999px;
}

.block-pre::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, rgba(79, 70, 229, 0.8), rgba(37, 99, 235, 0.75));
}

.summary-block .block-pre,
.sources-block .block-pre {
  max-height: 360px;
}


.tools-block {
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

.tools-block h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: 0.02em;
}

.tool-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-entry {
  background: rgba(248, 250, 252, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tool-entry-header {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.tool-entry-title {
  font-weight: 600;
  color: #1f2937;
}

.tool-entry-note {
  font-size: 12px;
  color: #0f766e;
}

.tool-entry-path {
  margin: 0;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #2563eb;
}

.tool-subtitle {
  margin: 0;
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}

.tool-pre {
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

.tool-pre::-webkit-scrollbar {
  width: 6px;
}

.tool-pre::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.7);
}

.tool-pre::-webkit-scrollbar-thumb {
  background: rgba(99, 102, 241, 0.7);
  border-radius: 10px;
}

.link-btn {
  background: none;
  border: none;
  color: #0369a1;
  cursor: pointer;
  padding: 0 4px;
  font-size: 12px;
  border-radius: 8px;
  transition: color 0.2s ease, background 0.2s ease;
}

.link-btn:hover {
  color: #0ea5e9;
  background: rgba(14, 165, 233, 0.16);
}


.sources-block,
.summary-block {
  position: relative;
  margin-top: 16px;
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.4);
}

.sources-history {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sources-history h4 {
  margin: 0;
  color: #1f2937;
  font-size: 14px;
  letter-spacing: 0.01em;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.history-list details {
  background: rgba(248, 250, 252, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  padding: 12px 16px;
  color: #1f2937;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.history-list details[open] {
  background: rgba(224, 231, 255, 0.55);
  border-color: rgba(129, 140, 248, 0.4);
}

.history-list summary {
  cursor: pointer;
  font-weight: 600;
  outline: none;
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.history-list summary::-webkit-details-marker {
  display: none;
}

.history-list summary::after {
  content: "▾";
  margin-left: 6px;
  font-size: 12px;
  opacity: 0.7;
  transition: transform 0.2s ease;
}

.history-list details[open] summary::after {
  transform: rotate(180deg);
}

.block-highlight {
  animation: glow 1.2s ease;
}

.sources-block h3,
.summary-block h3 {
  margin: 0 0 14px;
  color: #1f2937;
  letter-spacing: 0.02em;
}

.sources-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.source-item {
  position: relative;
  display: inline-flex;
  flex-direction: column;
  gap: 6px;
}

.source-link {
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
  letter-spacing: 0.01em;
  transition: color 0.2s ease;
}

.source-link::after {
  content: " ↗";
  font-size: 12px;
  opacity: 0.6;
}

.source-link:hover {
  color: #0f172a;
}

.source-tooltip {
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

.source-tooltip::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border-width: 10px;
  border-style: solid;
  border-color: rgba(255, 255, 255, 0.98) transparent transparent transparent;
}

.source-tooltip::before {
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

.source-tooltip p {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.6;
}

.source-tooltip p:last-child {
  margin-bottom: 0;
}

.muted-text {
  color: #64748b;
}

.source-item:hover .source-tooltip,
.source-item:focus-within .source-tooltip {
  display: block;
}

.hint.muted {
  color: #64748b;
}

@keyframes float {
  0% {
    transform: translate3d(0, 0, 0) rotate(0deg);
  }
  50% {
    transform: translate3d(10%, 6%, 0) rotate(3deg);
  }
  100% {
    transform: translate3d(0, 0, 0) rotate(0deg);
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.3);
    opacity: 0.5;
  }
}

@keyframes glow {
  0% {
    box-shadow: 0 0 0 rgba(59, 130, 246, 0.3);
    border-color: rgba(59, 130, 246, 0.5);
  }
  100% {
    box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.12);
    border-color: rgba(148, 163, 184, 0.2);
  }
}

@media (max-width: 960px) {
  .app-shell {
    padding: 56px 16px;
  }

  .layout {
    flex-direction: column;
    align-items: stretch;
  }

  .panel {
    padding: 22px;
  }

  .panel-form,
  .panel-result {
    max-width: none;
  }

  .status-bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .status-main,
  .status-controls {
    width: 100%;
  }

  .status-controls {
    justify-content: flex-start;
  }
}

@media (max-width: 600px) {
  .options {
    flex-direction: column;
  }

  .status-meta {
    font-size: 12px;
  }

  .panel-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .panel-form h1 {
    font-size: 24px;
  }
}

/* 侧边栏样式 */
.sidebar {
  width: 400px;
  min-width: 400px;
  height: 100vh;
  background: rgba(255, 255, 255, 0.98);
  border-right: 1px solid rgba(148, 163, 184, 0.2);
  padding: 32px 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  overflow-y: auto;
  box-shadow: 4px 0 24px rgba(15, 23, 42, 0.08);
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sidebar-header h2 {
  font-size: 24px;
  font-weight: 700;
  margin: 0;
  color: #1f2937;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 12px;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  width: fit-content;
}

.back-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.1);
  border-color: #3b82f6;
  color: #3b82f6;
}

.back-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.research-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-item label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #64748b;
}

.info-item p {
  margin: 0;
  font-size: 14px;
  color: #1f2937;
  line-height: 1.6;
}

.topic-display {
  font-size: 16px !important;
  font-weight: 600;
  color: #0f172a !important;
  padding: 12px;
  background: rgba(59, 130, 246, 0.05);
  border-radius: 8px;
  border-left: 3px solid #3b82f6;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: rgba(148, 163, 184, 0.2);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-text {
  font-size: 13px !important;
  color: #64748b !important;
  font-weight: 500;
}

.sidebar-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
}

.new-research-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 20px;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  border: none;
  border-radius: 12px;
  color: white;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.new-research-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
}

.new-research-btn:active {
  transform: translateY(0);
}

/* 全屏状态下的结果面板 */
.layout-fullscreen .panel-result {
  flex: 1;
  height: 100vh;
  border-radius: 0;
  border: none;
  overflow-y: auto;
  max-width: none;
}

@media (max-width: 1024px) {
  .sidebar {
    width: 320px;
    min-width: 320px;
  }
}

@media (max-width: 768px) {
  .layout-fullscreen {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    min-width: 100%;
    height: auto;
    max-height: 40vh;
  }

  .layout-fullscreen .panel-result {
    height: 60vh;
  }
}
</style>

<style scoped>
.p0-home{display:grid;grid-template-columns:minmax(400px,1fr) minmax(310px,400px);max-width:1250px;margin:40px auto;padding:24px;gap:24px;align-items:start}.p0-home .panel-centered{width:auto;max-width:none;margin:0}.p0-home .options{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:1000px){.p0-home{grid-template-columns:1fr;max-width:740px}}@media(max-width:600px){.p0-home{padding:12px;margin:0}.p0-home .options{grid-template-columns:1fr}}
</style>

<style scoped>
.p0-home{grid-template-columns:260px minmax(340px,1fr) 360px;max-width:1600px;width:100%;box-sizing:border-box;margin:0 auto;min-height:100vh;padding:28px;gap:22px}.home-sidebar{height:calc(100vh - 56px);display:flex;flex-direction:column;gap:22px;min-width:0;padding:16px 18px 16px 0;border-right:1px solid #e0e6f0}.home-sidebar h2{font-size:20px;color:#26344c;margin:0}.history-error{font-size:12px;color:#b42338;margin:0}.sidebar .research-info{flex:0 0 auto}.sidebar .sidebar-actions{flex-shrink:0}.sidebar{overflow:hidden;gap:18px}.p0-home .panel-centered{padding:30px}.p0-home .panel-head{gap:12px}.p0-home .panel-head h1{font-size:25px}@media(max-width:1250px){.p0-home{grid-template-columns:230px minmax(300px,1fr);padding:20px}.p0-home>.model-panel{grid-column:2}.home-sidebar{grid-row:1 / span 2;height:calc(100vh - 40px);position:sticky;top:20px}}@media(max-width:768px){.p0-home{grid-template-columns:1fr;padding:12px}.home-sidebar{position:static;height:300px;grid-row:auto;border-right:0;padding:0}.p0-home>.model-panel{grid-column:auto}.sidebar{height:auto;max-height:none;overflow:visible}.sidebar>.history{max-height:280px}.layout-fullscreen .panel-result{height:auto;min-height:60vh}}
</style>

<style scoped>
.app-shell:not(.expanded){padding:0;align-items:stretch;overflow:hidden;background:#f3f7ff}.p0-home .panel-centered:hover{transform:none}.p0-home .panel-centered{box-shadow:0 8px 28px #243a6010}.home-sidebar{flex-shrink:0}
</style>

<style scoped>
.sidebar-header{flex-shrink:0}.sidebar-scroll{flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column;gap:18px;padding-right:2px}.sidebar-scroll>.history{flex:1 0 180px}.sidebar-scroll>.timing-panel,.sidebar-scroll>.research-info{flex-shrink:0}@media(max-width:768px){.sidebar-scroll{min-height:300px;max-height:550px;flex:auto}}
</style>

<style scoped>
/* 首页三栏共享同一条网格轨道，各自滚动，不由内容撑高。 */
.app-shell:not(.expanded){height:100vh;min-height:0;overflow:auto;display:block}
.p0-home{height:100vh;min-height:0;max-width:1920px;min-width:1020px;grid-template-columns:240px minmax(340px,1fr) 340px;grid-template-rows:minmax(0,1fr);align-items:stretch;gap:22px;padding:24px;margin:0 auto}
.p0-home>.home-sidebar,.p0-home>.panel-centered,.p0-home>.model-panel{height:100%;min-height:0;max-height:100%;box-sizing:border-box;align-self:stretch;grid-row:1;grid-column:auto;position:relative;top:auto;margin:0}
.p0-home>.home-sidebar{padding:24px 18px;background:#ffffffa8;border:1px solid #e1e8f4;border-radius:20px;overflow:hidden;gap:22px}
.p0-home>.home-sidebar>.history{min-height:0}.p0-home>.home-sidebar>h2,.p0-home>.home-sidebar>.new-research-btn{flex-shrink:0}
.p0-home>.model-panel{overflow-y:auto}
.p0-home>.panel-centered{padding:24px;display:flex;flex-direction:column;background:#ffffff80;overflow:hidden;max-width:none}
.p0-home .home-welcome{flex:1;min-height:90px;overflow:auto;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;margin:0;padding:16px;gap:18px}
.p0-home .home-welcome .logo{width:68px;height:68px;flex-shrink:0}.p0-home .home-welcome h1{font-size:30px}.p0-home .home-welcome p{font-size:18px;color:#7e8ba5;margin-top:12px}
.home-composer{flex:0 1 auto;max-height:65%;overflow-y:auto;background:white;border:1px solid #e1e8f4;border-radius:16px;padding:20px;box-shadow:0 5px 20px #31559608}
.p0-home .form{gap:12px}.p0-home .form textarea{min-height:92px;height:100px;max-height:160px;resize:vertical}.p0-home .field{gap:7px}.p0-home .field span{font-size:13px}.p0-home .form select{padding:10px 12px}.p0-home .options{display:grid;grid-template-columns:1fr 1fr;gap:14px}.p0-home .form-actions{margin-top:0}.p0-home .hint{margin:0;font-size:12px}
@media(min-width:1600px){.p0-home{grid-template-columns:280px minmax(400px,1fr) 380px}}
</style>

<style scoped>
.detail-tabs{display:flex;align-items:center;gap:22px;border-bottom:1px solid #e2e8f3;margin-bottom:20px;min-width:0}.detail-tabs button{background:none;border:0;border-bottom:2px solid transparent;padding:10px 2px 12px;font-size:15px;font-weight:600;color:#7a89a4;cursor:pointer;overflow-wrap:anywhere;text-align:left}.detail-tabs button[aria-selected=true]{color:#3469e8;border-bottom-color:#3469e8}.detail-tabs button:focus-visible{outline:2px solid #9bb8f3;outline-offset:2px;border-radius:3px}#analysis-panel{display:flex;flex-direction:column;gap:20px;min-width:0}.task-detail{min-width:0}.summary-block,.report-block{min-width:0}
</style>

<style scoped>
.research-content{min-width:0}.research-tabs{display:flex;gap:20px;overflow-x:auto;max-width:100%;border-bottom:1px solid #dce5f4;background:white;padding:8px 20px 0;border-radius:16px 16px 0 0;scrollbar-width:thin}.research-tabs button{display:flex;align-items:center;gap:7px;flex-shrink:0;border:0;border-bottom:3px solid transparent;background:none;color:#65758e;font-size:14px;font-weight:600;padding:14px 0;cursor:pointer;white-space:nowrap}.research-tabs button[aria-selected=true]{color:#3469e8;border-bottom-color:#3469e8}.research-tabs button:focus-visible{outline:2px solid #99b9ff;outline-offset:-2px}.tab-state{width:6px;height:6px;border-radius:50%;background:#bbc6d7}.tab-state.completed{background:#42b88b}.tab-state.in_progress{background:#477bff}.tab-state.failed{background:#d86464}.research-content>.task-detail,.research-content>.report-block{border-radius:0 0 16px 16px;margin-top:0}.detail-tabs{gap:12px;border:0;margin-bottom:6px}.detail-tabs button{font-size:13px;border:0;border-radius:18px;padding:8px 16px;background:#f1f5fc}.detail-tabs button[aria-selected=true]{background:#386cff;color:white}
</style>

<style scoped>
/* Keep both research columns full height; scroll their contents instead of the background. */
.layout-fullscreen .panel-result{overflow:hidden;padding-bottom:0;background:#f3f6ff;min-width:0;box-sizing:border-box}
.layout-fullscreen .panel-result::before{display:none}
.layout-fullscreen .status-bar,.layout-fullscreen .timeline-wrapper,.layout-fullscreen .error-chip{flex-shrink:0}
.layout-fullscreen .tasks-section{flex:1;min-height:0;grid-template-columns:260px minmax(0,1fr);align-items:stretch;overflow:hidden}
.layout-fullscreen .tasks-list{height:100%;min-height:0;overflow-y:auto;box-sizing:border-box;background:#eaf2ff;border-radius:16px 16px 0 0;padding-bottom:24px}
.layout-fullscreen .research-content{height:100%;min-height:0;overflow-y:auto;overflow-x:hidden;background:white;border:1px solid #e1e8f4;border-bottom:0;border-radius:16px 16px 0 0;scrollbar-gutter:stable;box-sizing:border-box}
.layout-fullscreen .research-tabs{position:sticky;top:0;z-index:3;border-radius:0}
.layout-fullscreen .research-content>.task-detail,.layout-fullscreen .research-content>.report-block{border:0;box-shadow:none;min-height:calc(100% - 61px);box-sizing:border-box;padding:24px}
@media(max-width:1100px) and (min-width:769px){.layout-fullscreen .tasks-section{grid-template-columns:220px minmax(0,1fr);gap:14px}.layout-fullscreen .sidebar{width:280px;min-width:280px;padding:24px 18px}.layout-fullscreen .panel-result{padding:18px 14px 0}}
@media(max-width:768px){.layout-fullscreen .panel-result{height:auto;min-height:80vh;overflow:visible}.layout-fullscreen .tasks-section{min-height:70vh;grid-template-columns:180px minmax(0,1fr);gap:10px;overflow:visible}.layout-fullscreen .tasks-list{height:auto;min-height:100%;padding:12px}.layout-fullscreen .research-content{height:auto;min-height:70vh}.layout-fullscreen .research-content>.task-detail,.layout-fullscreen .research-content>.report-block{padding:14px}}
</style>

<style scoped>.task-list-head,.topic-label{display:flex;justify-content:space-between;align-items:center}.task-list-head button,.topic-label button{border:0;background:transparent;color:#4874c3;cursor:pointer}.task-list-head button:disabled,.topic-label button:disabled{opacity:.35;cursor:default}.content-shell{position:relative;min-width:0;min-height:0;height:100%;overflow:hidden}.editing-mask{position:absolute;inset:0;background:#54607180;backdrop-filter:blur(1px);z-index:10;display:grid;place-items:center;color:white;font-weight:600;padding:20px;text-align:center}.layout-fullscreen .tasks-section.editing{grid-template-columns:320px minmax(0,1fr)}</style>
<style scoped>.note-action{border:1px solid #d9e3f3;background:white;color:#3b6cc0;border-radius:7px;padding:6px 12px;cursor:pointer}.home-note-overlay{position:fixed;z-index:20;top:24px;bottom:24px;left:330px;right:24px;background:white;border:1px solid #dce5f2;border-radius:16px;overflow:auto;box-shadow:0 12px 50px #273f5720}.home-note-overlay nav{position:sticky;top:0;background:white;padding:12px 24px;border-bottom:1px solid #dce5f2;z-index:2}.home-note-overlay nav button{background:#edf3ff;color:#3970d2;border:0;border-radius:7px;padding:8px 18px}.home-note-overlay nav span{margin-left:12px;cursor:pointer}.home-sidebar .note-list{flex:0 1 220px;overflow:auto}.sidebar-scroll>.note-list{flex-shrink:0}.research-tabs button span[role=button]{padding:2px 5px;margin-left:5px}.layout-fullscreen:has(.chat-panel) .sidebar{width:270px;min-width:270px;padding:24px 16px}.layout-fullscreen:has(.chat-panel) .tasks-section{grid-template-columns:210px minmax(0,1fr)}@media(max-width:1400px){.layout-fullscreen>.chat-panel{position:fixed;right:0;top:0;z-index:30;box-shadow:-8px 0 28px #24395720}}</style>
<style scoped>.topic-dialog{border:1px solid #dce5f3;border-radius:16px;padding:24px;width:420px;color:#293951}.topic-dialog::backdrop{background:#14243f55}.topic-dialog h3{margin-top:0}.topic-dialog textarea{width:100%;box-sizing:border-box;padding:12px;border:1px solid #d0dcee;border-radius:8px;font:inherit}.topic-dialog p{font-size:13px;line-height:1.7;color:#bb4051}.topic-dialog>div{display:flex;justify-content:flex-end;gap:10px}.topic-dialog button{border:0;border-radius:7px;padding:10px 16px;background:#e7f5ed;color:#167958;cursor:pointer}.topic-dialog .confirm{background:#d94253;color:white}</style>
<style scoped>
.app-shell.expanded{overflow-x:auto}.layout-fullscreen{gap:0;flex-direction:row}.layout-fullscreen .sidebar{width:var(--sidebar-width)!important;min-width:var(--sidebar-width)!important;padding:24px 18px;box-sizing:border-box}.layout-fullscreen .panel-result{flex:1;width:0;padding:20px 18px 0;min-width:0}.layout-fullscreen .tasks-section,.layout-fullscreen .tasks-section.editing{grid-template-columns:var(--tasks-width) 10px minmax(0,1fr)!important;gap:0}.layout-fullscreen>.chat-panel{position:relative!important;top:auto!important;right:auto!important;width:var(--chat-width)!important;min-width:var(--chat-width)!important;box-shadow:none!important;flex-shrink:0}.task-status{white-space:nowrap;flex-shrink:0}
</style>

<style scoped>.task-card-head{display:flex;align-items:flex-start;gap:6px;padding:12px 12px 6px}.task-card-head .task-button{padding:0;min-width:0;flex:1}.task-card-head>.task-status{margin-top:0;border:0}.retry-task{cursor:pointer}.retry-task:hover{box-shadow:0 0 0 2px #d1def4}.retry-task:disabled{cursor:wait;opacity:.6}.task-status.paused,.task-status.interrupted{background:#fff2d8;color:#9b671b}.report-update-notice{margin:14px 20px 0;padding:12px 16px;border-radius:9px;background:#fff7e4;color:#9b6917;font-size:13px;line-height:1.6}</style>

<style scoped>
.chat-slot{width:var(--chat-width);min-width:300px;height:100%;flex-shrink:0}.chat-slot :deep(.chat-panel){width:100%;height:100%}
</style>

<style scoped>
.home-mode-actions{display:flex;flex-direction:column;gap:10px;flex-shrink:0}.home-mode-actions .new-research-btn{height:48px;min-height:48px;width:100%;box-sizing:border-box;display:flex;align-items:center;justify-content:center;gap:8px}.home-mode-actions .modeSelected{outline:2px solid #a8bcff;outline-offset:3px}.home-conversation-history{flex:1;min-height:0;display:flex;flex-direction:column}.p0-home>.home-chat-panel{height:100%;min-height:0;max-height:100%;min-width:0;box-sizing:border-box;grid-row:1;border:1px solid #e1e8f4;border-radius:20px;overflow:hidden;background:linear-gradient(135deg,#edf3ff,#f0edff)}#home-chat-slot{height:100%;min-height:0;width:100%}
</style>

<style scoped>
.content-shell{overflow-x:auto}.document-panes{display:flex;height:100%;min-height:0;min-width:0}.document-panes.split{min-width:650px}.document-panes>.research-content{flex:1;min-width:0}.document-panes.split>.research-content{flex:0 0 clamp(280px, var(--document-left), calc(100% - 290px))}.comparison-pane{flex:1;min-width:280px;height:100%;overflow:auto;scrollbar-gutter:stable;background:white;border:1px solid #e1e8f4;border-radius:16px 16px 0 0;box-sizing:border-box}.comparison-header{position:sticky;top:0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 18px;background:white;border-bottom:1px solid #dce5f4;min-height:33px}.comparison-header button{border:0;background:transparent;color:#3469e8;cursor:pointer}.comparison-title{font-size:14px;font-weight:600;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.comparison-title[draggable],.research-tabs button[draggable]{cursor:grab}.close-comparison{font-size:22px}.comparison-document{padding:24px}.comparison-sources{font-size:13px;line-height:1.8;margin-bottom:24px}.comparison-sources a{color:#3269e8;overflow-wrap:anywhere}.document-drop-overlay{position:absolute;inset:0;z-index:8;pointer-events:none;display:flex;gap:12px;padding:70px 12px 12px}.document-drop-zone{width:50%;border:2px dashed #6d96f1;border-radius:12px;background:#edf3ffe8;color:#3568c9;display:grid;place-items:center;text-align:center;pointer-events:auto;font-weight:600}.document-drop-zone:hover{background:#dce8fff2;border-color:#3c6ff0}.comparison-error{position:absolute;bottom:12px;left:12px;right:12px;padding:12px;background:#fff0f0;color:#b13c48;border-radius:8px;z-index:9}.comparison-pane :deep(.note-editor){min-height:calc(100% - 63px)}
</style>

<style scoped>
.research-tabs{gap:7px;padding-top:8px}.research-tabs button{background:transparent;color:#6c7584;border-radius:7px 7px 0 0;padding:12px 12px;border-bottom:3px solid transparent}.research-tabs button[aria-selected=true]{background:transparent;color:#3469e8;border-bottom-color:#3469e8}.comparison-header{padding:0;gap:0;min-height:0;align-items:stretch}.comparison-header>.research-tabs{flex:1;min-width:0;border-bottom:0;position:static;border-radius:0}.comparison-header>.close-comparison{flex:0 0 36px;width:36px;padding:0;background:white}.comparison-header .research-tabs button{border-bottom:3px solid transparent}.comparison-header .research-tabs button[aria-selected=true]{border-bottom-color:#3469e8}.research-content .research-tabs,.comparison-header{min-height:61px;box-sizing:border-box}.research-tabs button{max-width:250px;overflow:hidden;text-overflow:ellipsis}.home-note-overlay nav{display:flex;gap:8px;overflow-x:auto}.home-note-overlay nav button{white-space:nowrap}
</style>
