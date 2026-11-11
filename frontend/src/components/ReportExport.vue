
<template>
  <div class="report-export">
    <button
      type="button"
      class="export-btn"
      :disabled="!markdown.trim() || exporting"
      @click="downloadMarkdown"
    >
      MD
    </button>

    <button
      type="button"
      class="export-btn"
      :disabled="!markdown.trim() || exporting"
      @click="downloadWord"
    >
      {{ exporting ? "导出中..." : "Word" }}
    </button>

    <button
      type="button"
      class="export-btn"
      :disabled="!markdown.trim()"
      @click="exportPdf"
    >
      PDF
    </button>

    <span v-if="error" class="export-error" role="alert">
      {{ error }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

const props = defineProps<{
  markdown: string;
  title?: string;
}>();

const exporting = ref(false);
const error = ref("");

function safeFilename(name: string) {
  return name.replace(/[\\/:*?"<>|]/g, "_").trim() || "研究报告";
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(url);
}

function downloadMarkdown() {
  error.value = "";

  const blob = new Blob(
    ["\uFEFF", props.markdown],
    { type: "text/markdown;charset=utf-8" }
  );

  downloadBlob(
    blob,
    safeFilename(props.title || "研究报告") + ".md"
  );
}

async function downloadWord() {
  if (!props.markdown.trim() || exporting.value) return;

  exporting.value = true;
  error.value = "";

  try {
    const response = await fetch(
      "http://127.0.0.1:8000/export/word",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          title: props.title || "研究报告",
          markdown: props.markdown
        })
      }
    );

    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(
        data?.detail || `Word 导出失败：${response.status}`
      );
    }

    const blob = await response.blob();

    downloadBlob(
      blob,
      safeFilename(props.title || "研究报告") + ".docx"
    );
  } catch (e) {
    error.value = e instanceof Error
      ? e.message
      : "Word 导出失败，请检查后端服务";
  } finally {
    exporting.value = false;
  }
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char] || char);
}

function exportPdf() {
  error.value = "";

  const printWindow = window.open("", "_blank");

  if (!printWindow) {
    error.value = "浏览器拦截了打印窗口，请允许弹出窗口后重试";
    return;
  }

  const content = DOMPurify.sanitize(
      marked.parse(props.markdown, { async: false }) as string,
      {
        USE_PROFILES: { html: true },
        FORBID_TAGS: ["script", "iframe", "form", "input", "button"],
        FORBID_ATTR: ["style", "id", "name"]
      }
  );

  printWindow.document.open();
  printWindow.document.write(`
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
      <meta charset="UTF-8">
      <title>${escapeHtml(props.title || "研究报告")}</title>
      <style>
        @page {
          size: A4;
          margin: 22mm 20mm;
        }
        body {
          font-family: "Microsoft YaHei", "SimSun", sans-serif;
          color: #222;
          line-height: 1.85;
          font-size: 12pt;
          overflow-wrap: anywhere;
        }
        h1 { font-size: 24pt; }
        h2 { font-size: 19pt; margin-top: 25px; }
        h3 { font-size: 15pt; margin-top: 20px; }
        pre {
          white-space: pre-wrap;
          background: #f4f4f4;
          padding: 12px;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          margin: 15px 0;
        }
        td, th {
          border: 1px solid #999;
          padding: 7px;
        }
        th { background: #eee; }

        .markdown-content {
          font-family: "Microsoft YaHei", "SimSun", sans-serif;
          line-height: 1.85;
        }
        .markdown-content h1,
        .markdown-content h2,
        .markdown-content h3 {
          page-break-after: avoid;
        }
        .markdown-content p {
          margin: 12px 0;
        }
        .markdown-content img {
          max-width: 100%;
        }
        .markdown-content ul,
        .markdown-content ol {
          padding-left: 28px;
        }

        @media print {
          a { color: #222; text-decoration: none; }
          pre, table, blockquote {
            break-inside: avoid;
          }
        }
      </style>
    </head>
    <body>
      <h1>${escapeHtml(props.title || "研究报告")}</h1>
      <div class="markdown-content">${content}</div>
      <script>
        window.onload = function() {
          window.print();
        };
      <\/script>
    </body>
    </html>
  `);
  printWindow.document.close();
}
</script>

<style scoped>
.report-export {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.export-btn {
  border: 1px solid #dbe3ef;
  background: #f7f9fc;
  color: #405577;
  border-radius: 7px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all .2s ease;
}

.export-btn:hover {
  background: #eaf1ff;
  border-color: #9bb8ef;
  color: #2458b5;
}

.export-btn:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.export-error {
  color: #c03945;
  font-size: 12px;
}
</style>
