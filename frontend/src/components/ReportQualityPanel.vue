<template>
  <button
    ref="buttonEl"
    class="note-action quality-entry"
    type="button"
    :disabled="!runId"
    :aria-expanded="open"
    title="报告质检：核验引用来源、结构与交付规范"
    @click="togglePanel"
  >
    <span class="quality-grade" :class="gradeClass">{{ audit?.grade || "检" }}</span>
    <span>质检</span>
  </button>
  <button
    class="note-action quality-mark-toggle"
    type="button"
    :class="{ active: markersOn }"
    :disabled="!runId || !audit"
    :title="markersOn ? '关闭原文标记（不改动报告内容）' : '在原文中标记问题位置'"
    @click="toggleMarkers"
  >
    <span class="mark-dot" />
    <span>{{ markersOn ? `标记 ${markedCount}` : "标记" }}</span>
  </button>

  <Teleport to="body">
    <div v-if="open" class="rqg-backdrop" @click.self="closePanel"></div>
    <aside v-if="open" class="rqg-panel" role="dialog" aria-label="报告质检">
      <header class="rqg-head">
        <div>
          <h3>报告质检</h3>
          <p class="rqg-sub">核验引用是否可追溯、结构是否完整、是否适合交付</p>
        </div>
        <button class="rqg-close" type="button" aria-label="关闭质检面板（保留原文标记）" @click="closePanel">×</button>
      </header>

      <div v-if="loading" class="rqg-state">正在读取报告与来源…</div>
      <div v-else-if="error" class="rqg-state rqg-error">
        {{ error }}
        <button type="button" class="rqg-retry" @click="load()">重试</button>
      </div>
      <div v-else-if="audit" class="rqg-body">
        <div class="rqg-score">
          <div class="rqg-score-ring" :class="gradeClass">
            <strong>{{ audit.score }}</strong>
            <small>/100</small>
          </div>
          <div class="rqg-score-meta">
            <p>
              <span class="rqg-grade" :class="gradeClass">等级 {{ audit.grade }}</span>
              <span v-if="audit.report_available">共 {{ issueCount }} 处问题</span>
              <span v-else>尚未生成最终报告</span>
            </p>
            <p class="rqg-muted">{{ summaryText }}</p>
          </div>
        </div>

        <div class="rqg-metrics">
          <div class="rqg-metric"><b>{{ audit.metrics.cited_unique }}</b><span>去重引用</span></div>
          <div class="rqg-metric"><b>{{ audit.metrics.inline_citations }}</b><span>行内引用</span></div>
          <div class="rqg-metric rqg-danger"><b>{{ audit.metrics.unverified }}</b><span>疑似编造</span></div>
          <div class="rqg-metric"><b>{{ audit.metrics.sections_without_source }}</b><span>无来源章节</span></div>
        </div>

        <p class="rqg-hint">
          关闭本面板不会清除原文标记；标记由工具栏独立的「标记」按钮控制。
        </p>

        <div class="rqg-tabs" role="tablist">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            role="tab"
            :aria-selected="activeTab === tab.id"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>

        <div v-if="activeTab === 'issues'" class="rqg-list">
          <p v-if="!audit.issues.length" class="rqg-empty">未发现问题，报告可以直接交付。</p>
          <button
            v-for="(issue, index) in audit.issues"
            :key="`${issue.type}-${index}`"
            type="button"
            class="rqg-issue"
            :class="`is-${issue.severity}`"
            @click="locate({ section: issue.section, snippet: issue.snippet })"
          >
            <span class="rqg-sev">{{ SEVERITY_LABELS[issue.severity] }}</span>
            <span class="rqg-issue-body">
              <strong>{{ ISSUE_LABELS[issue.type] || issue.type }}</strong>
              <span>{{ issue.message }}</span>
              <em v-if="issue.section">位置：{{ issue.section }}<template v-if="issue.line !== undefined"> · 第 {{ issue.line + 1 }} 行</template></em>
              <em v-else-if="issue.task_id">任务 {{ issue.task_id }}</em>
            </span>
          </button>
        </div>

        <div v-else-if="activeTab === 'sources'" class="rqg-list">
          <p v-if="!audit.sources.length" class="rqg-empty">本次研究没有记录到来源。</p>
          <button
            v-for="source in audit.sources"
            :key="source.url"
            type="button"
            class="rqg-source"
            :disabled="!citationFor(source)"
            @click="locateCitation(citationFor(source))"
          >
            <span class="rqg-source-index">{{ source.index }}</span>
            <span class="rqg-source-body">
              <strong>{{ source.title }}</strong>
              <span>{{ source.domain }}</span>
              <em>
                {{ source.cited ? "已引用" : "未引用" }}
                <template v-if="!source.verified"> · 未在检索结果中</template>
                <template v-if="source.task_ids.length"> · 任务 {{ source.task_ids.join(",") }}</template>
              </em>
              <em v-if="citationFor(source)">
                位置：{{ citationFor(source)?.section }} · 第 {{ (citationFor(source)?.line ?? 0) + 1 }} 行
                <template v-if="citationFor(source)?.in_reference">（参考文献段）</template>
              </em>
            </span>
          </button>
        </div>

        <div v-else-if="activeTab === 'citations'" class="rqg-list">
          <p v-if="!audit.citations.length" class="rqg-empty">报告里没有任何链接。</p>
          <button
            v-for="(citation, index) in audit.citations"
            :key="`${citation.line}-${index}`"
            type="button"
            class="rqg-citation"
            @click="locateCitation(citation)"
          >
            <span class="rqg-citation-line">{{ citation.line + 1 }}</span>
            <span class="rqg-citation-body">
              <strong>{{ citation.section || "（无标题段）" }}</strong>
              <span>{{ citation.snippet || citation.title || citation.url }}</span>
              <em>
                {{ citation.form }}
                <template v-if="citation.in_reference"> · 参考文献段</template>
                <template v-else> · 正文行内</template>
              </em>
            </span>
          </button>
        </div>

        <div v-else class="rqg-list">
          <div class="rqg-report-actions">
            <button type="button" :disabled="reportLoading" @click="buildReport">
              {{ reportLoading ? "生成中…" : "生成质检单" }}
            </button>
            <button type="button" :disabled="!reportPayload" @click="copyReport">复制 Markdown</button>
          </div>
          <p v-if="reportError" class="rqg-state rqg-error">{{ reportError }}</p>
          <pre v-if="reportPayload" class="rqg-preview">{{ reportPayload.markdown }}</pre>
          <pre v-if="reportPayload" class="rqg-preview">{{ reportPayload.references_markdown }}</pre>
          <p v-if="!reportPayload && !reportLoading" class="rqg-empty">
            生成一份可直接附在报告后的质检单（含指标、问题清单与规范参考文献表）。
          </p>
        </div>
      </div>
    </aside>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  fetchQualityAudit,
  fetchQualityReport,
  ISSUE_LABELS,
  SEVERITY_LABELS,
  type QualityAudit,
  type QualityCitation,
  type QualityIssue,
  type QualityReportPayload,
  type QualitySource
} from "../services/quality";
import { QualityMarkerLayer, type MarkerTarget } from "./QualityMarkerLayer";

const props = defineProps<{ runId?: string; report: string }>();

const buttonEl = ref<HTMLButtonElement | null>(null);
const open = ref(false);
const loading = ref(false);
const error = ref("");
const audit = ref<QualityAudit | null>(null);
const activeTab = ref<"issues" | "sources" | "citations" | "report">("issues");
const reportPayload = ref<QualityReportPayload | null>(null);
const reportLoading = ref(false);
const reportError = ref("");
const markersOn = ref(false);
const markedCount = ref(0);

let markerLayer: QualityMarkerLayer | null = null;

const storageKey = computed(() => `rqg:markers:${props.runId || "none"}`);
const tabs = computed(() => [
  { id: "issues" as const, label: `问题 ${audit.value?.issues.length || 0}` },
  { id: "sources" as const, label: `来源 ${audit.value?.sources.length || 0}` },
  { id: "citations" as const, label: `引用位置 ${audit.value?.citations.length || 0}` },
  { id: "report" as const, label: "质检单" }
]);
const issueCount = computed(() => audit.value?.issues.length || 0);
const gradeClass = computed(() => `grade-${audit.value?.grade?.toLowerCase() || "x"}`);
const summaryText = computed(() => {
  const metrics = audit.value?.metrics;
  if (!metrics) return "";
  const coverage = Math.round((metrics.coverage || 0) * 100);
  return `引用可核验率 ${coverage}% · 检索来源 ${metrics.retrieved_unique} 条 · 未被引用 ${metrics.uncited} 条`;
});

function ensureLayer(): QualityMarkerLayer {
  if (!markerLayer) markerLayer = new QualityMarkerLayer(buttonEl.value);
  return markerLayer;
}

function citationFor(source: QualitySource): QualityCitation | null {
  if (!audit.value) return null;
  return (
    audit.value.citations.find((citation) => citation.url === source.url) ||
    audit.value.citations.find(
      (citation) => citation.title && citation.title === source.title && !citation.in_reference
    ) ||
    null
  );
}

async function load(quiet = false) {
  if (!props.runId) return;
  if (!quiet) loading.value = true;
  error.value = "";
  try {
    const data = await fetchQualityAudit(props.runId);
    audit.value = data;
    reportPayload.value = null;
    reportError.value = "";
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "质检数据加载失败";
  } finally {
    loading.value = false;
    await nextTick();
    if (markersOn.value) applyMarkers();
  }
}

async function togglePanel() {
  if (open.value) {
    closePanel();
    return;
  }
  open.value = true;
  activeTab.value = "issues";
  if (!audit.value) await load();
}

/** 关闭面板只关闭面板，原文标记保持（由工具栏「标记」按钮独立控制）。 */
function closePanel() {
  open.value = false;
}

function applyMarkers() {
  const layer = ensureLayer();
  layer.refresh(buttonEl.value);
  if (!audit.value) return;
  markedCount.value = layer.apply(audit.value.issues);
}

function clearMarkers() {
  markerLayer?.clear();
  markedCount.value = 0;
}

async function toggleMarkers() {
  markersOn.value = !markersOn.value;
  try {
    localStorage.setItem(storageKey.value, markersOn.value ? "1" : "0");
  } catch {
    /* 隐私模式忽略 */
  }
  if (!markersOn.value) {
    clearMarkers();
    return;
  }
  if (!audit.value) await load(true);
  await nextTick();
  applyMarkers();
}

function locate(target: MarkerTarget) {
  const layer = ensureLayer();
  layer.refresh(buttonEl.value);
  if (!layer.locate(target)) {
    error.value = "没能在原文中定位到该位置，可能报告已更新";
    window.setTimeout(() => {
      error.value = "";
    }, 2500);
  }
}

function locateCitation(citation: QualityCitation | null) {
  if (!citation) return;
  locate({ section: citation.section, snippet: citation.snippet });
}

async function buildReport() {
  if (!props.runId || reportLoading.value) return;
  reportLoading.value = true;
  reportError.value = "";
  try {
    reportPayload.value = await fetchQualityReport(props.runId);
    activeTab.value = "report";
  } catch (exception) {
    reportError.value = exception instanceof Error ? exception.message : "质检单生成失败";
  } finally {
    reportLoading.value = false;
  }
}

async function copyReport() {
  if (!reportPayload.value) return;
  const text = `${reportPayload.value.markdown}\n\n${reportPayload.value.references_markdown}`;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    reportError.value = "复制失败，请检查剪贴板权限";
  }
}

watch(
  () => props.runId,
  async () => {
    audit.value = null;
    open.value = false;
    clearMarkers();
    markersOn.value = false;
    try {
      markersOn.value = localStorage.getItem(storageKey.value) === "1";
    } catch {
      markersOn.value = false;
    }
    if (markersOn.value) {
      await load(true);
      await nextTick();
      applyMarkers();
    }
  }
);

watch(
  () => props.report,
  async () => {
    if (!markersOn.value) return;
    await nextTick();
    applyMarkers();
  }
);

onMounted(async () => {
  try {
    markersOn.value = localStorage.getItem(storageKey.value) === "1";
  } catch {
    markersOn.value = false;
  }
  if (markersOn.value) {
    await load(true);
    await nextTick();
    applyMarkers();
  }
});

onBeforeUnmount(() => {
  clearMarkers();
  markerLayer = null;
});
</script>

<style scoped>
.quality-entry { display: inline-flex; align-items: center; gap: 6px; }
.quality-mark-toggle { display: inline-flex; align-items: center; gap: 6px; }
.quality-mark-toggle .mark-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #cbd6e8;
}
.quality-mark-toggle.active { color: #b06a00; }
.quality-mark-toggle.active .mark-dot { background: #e0a500; box-shadow: 0 0 0 3px #ffe9b3; }
.quality-grade {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; border-radius: 50%;
  font-size: 11px; font-weight: 700; color: #fff; background: #8b9ab5;
}
.quality-grade.grade-a { background: #2f9e44; }
.quality-grade.grade-b { background: #2b6cd4; }
.quality-grade.grade-c { background: #c98a00; }
.quality-grade.grade-d { background: #c0392b; }

.rqg-backdrop { position: fixed; inset: 0; background: #14203a33; z-index: 940; }
.rqg-panel {
  position: fixed; top: 0; right: 0; height: 100vh; width: min(440px, 92vw);
  background: #fff; box-shadow: -8px 0 32px #18264026; z-index: 950;
  display: flex; flex-direction: column; font-size: 13px; color: #34415a;
}
.rqg-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 18px 20px 12px; border-bottom: 1px solid #e8eef8;
}
.rqg-head h3 { margin: 0 0 4px; font-size: 16px; color: #1c2b47; }
.rqg-sub { margin: 0; color: #7a88a4; font-size: 12px; }
.rqg-close { border: 0; background: transparent; font-size: 22px; line-height: 1; color: #7a88a4; cursor: pointer; }
.rqg-close:hover { color: #2b4a7d; }
.rqg-state { padding: 32px 20px; color: #6f809e; }
.rqg-error { color: #b83c48; }
.rqg-retry { margin-left: 8px; border: 1px solid #e0c2c7; background: #fff5f6; color: #b83c48; border-radius: 6px; padding: 3px 8px; cursor: pointer; }
.rqg-body { padding: 16px 20px 24px; overflow-y: auto; }
.rqg-score { display: flex; gap: 14px; align-items: center; margin-bottom: 14px; }
.rqg-score-ring {
  width: 64px; height: 64px; border-radius: 50%; display: flex; flex-direction: column;
  align-items: center; justify-content: center; color: #fff; background: #8b9ab5; flex-shrink: 0;
}
.rqg-score-ring strong { font-size: 20px; line-height: 1; }
.rqg-score-ring small { font-size: 10px; opacity: .85; }
.rqg-score-ring.grade-a { background: #2f9e44; }
.rqg-score-ring.grade-b { background: #2b6cd4; }
.rqg-score-ring.grade-c { background: #c98a00; }
.rqg-score-ring.grade-d { background: #c0392b; }
.rqg-score-meta p { margin: 0 0 5px; }
.rqg-grade { font-weight: 700; margin-right: 8px; }
.rqg-grade.grade-a { color: #2f9e44; } .rqg-grade.grade-b { color: #2b6cd4; }
.rqg-grade.grade-c { color: #c98a00; } .rqg-grade.grade-d { color: #c0392b; }
.rqg-muted { color: #7a88a4; font-size: 12px; }
.rqg-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 10px; }
.rqg-metric { background: #f5f8ff; border: 1px solid #e4ecfa; border-radius: 8px; padding: 8px 6px; text-align: center; }
.rqg-metric b { display: block; font-size: 17px; color: #1c2b47; }
.rqg-metric span { font-size: 11px; color: #6f809e; }
.rqg-danger b { color: #c0392b; }
.rqg-hint { margin: 0 0 12px; font-size: 11px; color: #8b9ab5; }
.rqg-tabs { display: flex; gap: 4px; border-bottom: 1px solid #e8eef8; margin-bottom: 10px; flex-wrap: wrap; }
.rqg-tabs button {
  border: 0; background: transparent; padding: 8px 8px; cursor: pointer;
  color: #6f809e; border-bottom: 2px solid transparent; font-size: 12px;
}
.rqg-tabs button.active { color: #2b6cd4; border-bottom-color: #2b6cd4; font-weight: 600; }
.rqg-list { display: flex; flex-direction: column; gap: 8px; max-height: 46vh; overflow-y: auto; }
.rqg-empty { color: #7a88a4; font-size: 12px; }
.rqg-issue {
  display: flex; gap: 8px; text-align: left; width: 100%; cursor: pointer;
  border: 1px solid #e6ecf6; background: #fff; border-radius: 8px; padding: 8px 10px;
}
.rqg-issue:hover { border-color: #bfd2f2; background: #f8fbff; }
.rqg-issue.is-error { border-left: 3px solid #c0392b; }
.rqg-issue.is-warn { border-left: 3px solid #c98a00; }
.rqg-issue.is-info { border-left: 3px solid #7a88a4; }
.rqg-sev { flex-shrink: 0; font-size: 11px; color: #6f809e; }
.rqg-issue-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.rqg-issue-body strong { font-size: 12px; color: #1c2b47; }
.rqg-issue-body span { font-size: 12px; color: #4d5e7d; }
.rqg-issue-body em { font-style: normal; font-size: 11px; color: #8b9ab5; }
.rqg-source, .rqg-citation {
  display: flex; gap: 8px; text-align: left; width: 100%; cursor: pointer;
  border: 1px solid #eef2f9; background: #fff; border-radius: 8px; padding: 7px 9px;
}
.rqg-source:hover, .rqg-citation:hover { border-color: #bfd2f2; background: #f8fbff; }
.rqg-source:disabled { cursor: default; opacity: .75; }
.rqg-source-index { color: #8b9ab5; font-size: 11px; width: 18px; flex-shrink: 0; }
.rqg-source-body, .rqg-citation-body { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.rqg-source-body strong, .rqg-citation-body strong { font-size: 12px; color: #22314e; overflow-wrap: anywhere; }
.rqg-source-body span, .rqg-citation-body span {
  font-size: 11px; color: #7a88a4; overflow-wrap: anywhere;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.rqg-source-body em, .rqg-citation-body em { font-style: normal; font-size: 11px; color: #8b9ab5; }
.rqg-citation-line { color: #8b9ab5; font-size: 11px; width: 26px; flex-shrink: 0; }
.rqg-report-actions { display: flex; gap: 8px; margin-bottom: 8px; }
.rqg-report-actions button {
  border: 1px solid #cfdcf2; background: #f5f8ff; color: #2b4a7d;
  border-radius: 6px; padding: 6px 10px; cursor: pointer; font-size: 12px;
}
.rqg-report-actions button:disabled { opacity: .5; cursor: default; }
.rqg-preview {
  white-space: pre-wrap; overflow-wrap: anywhere; background: #f8fafd;
  border: 1px solid #e9eff8; border-radius: 8px; padding: 10px;
  font-size: 11px; line-height: 1.6; max-height: 32vh; overflow-y: auto;
}
</style>

<style>
/* 标记类作用于 MarkdownDocument 渲染出的 DOM，必须保持非 scoped。 */
.rqg-flagged {
  background: #fff7d6 !important;
  box-shadow: inset 3px 0 0 #e0a500;
  border-radius: 3px;
}
.rqg-flagged.rqg-flash { animation: rqg-flash 2.4s ease-out; }
@keyframes rqg-flash {
  0% { background: #ffd75e; }
  100% { background: #fff7d6; }
}
.rqg-inline-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 15px; height: 15px; margin-left: 6px; border-radius: 50%;
  font-size: 10px; font-weight: 700; color: #fff; background: #7a88a4;
  vertical-align: middle; cursor: help;
}
.rqg-inline-badge[data-rqg-badge="error"] { background: #c0392b; }
.rqg-inline-badge[data-rqg-badge="warn"] { background: #c98a00; }
</style>
