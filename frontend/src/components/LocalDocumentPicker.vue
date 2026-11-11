
<template>
  <section class="local-library" aria-label="本地文献资料库">

    <div class="library-heading">
      <div>
        <strong>本地文献资料</strong>
        <span class="library-count">
          {{ documents.length }} 篇
        </span>
      </div>

      <button
        type="button"
        class="upload-button"
        :disabled="disabled || uploading"
        @click="chooseFiles"
      >
        <span aria-hidden="true">＋</span>
        {{ uploading ? '正在导入…' : '导入文献' }}
      </button>

      <input
        ref="fileInput"
        class="visually-hidden"
        type="file"
        accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
        multiple
        @change="handleFiles"
      />
    </div>

    <p class="library-hint">
      勾选文献后，AI 会同时检索本地资料和互联网资料。
      支持 PDF、Word、TXT、Markdown，单个文件最大 25 MB。
      原文件保存在本机；命中的文本片段会发送给当前选定的模型进行分析。
    </p>

    <div v-if="loading" class="library-state">
      正在加载本地文献…
    </div>

    <div v-else-if="!documents.length" class="library-empty">
      <span class="empty-icon" aria-hidden="true">▤</span>
      <span>
        还没有导入文献。点击“导入文献”添加你的论文或研究资料。
      </span>
    </div>

    <div v-else class="document-list">

      <label
        v-for="doc in documents"
        :key="doc.id"
        class="document-row"
        :class="{
          selected: selectedIds.includes(doc.id)
        }"
      >

        <input
          type="checkbox"
          :checked="selectedIds.includes(doc.id)"
          :disabled="
            disabled ||
            (
              !selectedIds.includes(doc.id) &&
              selectedIds.length >= 20
            )
          "
          @change="onCheckboxChange($event, doc.id)"
        />

        <span class="file-type">
          {{ doc.extension.replace('.', '').toUpperCase() }}
        </span>

        <span class="document-meta">
          <strong :title="doc.title">
            {{ doc.title }}
          </strong>

          <small>
            {{ formatSize(doc.size_bytes) }}
            · {{ doc.chunk_count }} 个文本片段
            <span v-if="doc.page_count">
              · {{ doc.page_count }} 页
            </span>
          </small>
        </span>

        <button
          type="button"
          class="icon-button"
          :disabled="disabled || uploading"
          title="从资料库删除"
          :aria-label="`删除 ${doc.title}`"
          @click.prevent="removeDocument(doc)"
        >
          ×
        </button>

      </label>

    </div>

    <div v-if="selectedIds.length" class="selection-footer">
      已选择 {{ selectedIds.length }} 篇文献参与本次研究
    </div>

    <p
      v-if="message"
      class="library-message"
      :class="{ error: messageType === 'error' }"
      role="status"
    >
      {{ message }}
    </p>

  </section>
</template>

<script setup lang="ts">

import { onMounted, ref } from "vue";
import { api } from "../services/api";

interface LocalDocument {
  id: string;
  title: string;
  extension: string;
  size_bytes: number;
  chunk_count: number;
  page_count: number | null;
  created_at: string;
}

const props = withDefaults(
  defineProps<{
    selectedIds: string[];
    disabled?: boolean;
  }>(),
  {
    disabled: false
  }
);

const emit = defineEmits<{
  (event: "update:selectedIds", value: string[]): void;
}>();

const apiBase =
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:8000";

const documents = ref<LocalDocument[]>([]);

const fileInput = ref<HTMLInputElement | null>(null);

const loading = ref(false);

const uploading = ref(false);

const message = ref("");

const messageType = ref<"success" | "error">("success");

function chooseFiles() {

  if (!props.disabled && !uploading.value) {
    fileInput.value?.click();
  }

}

function formatSize(bytes: number): string {

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;

}

async function loadDocuments() {

  loading.value = true;

  try {

    documents.value = await api<LocalDocument[]>(
      "/documents"
    );

    const valid = new Set(
      documents.value.map(item => item.id)
    );

    const retained = props.selectedIds.filter(
      id => valid.has(id)
    );

    if (
      retained.length !== props.selectedIds.length
    ) {
      emit("update:selectedIds", retained);
    }

  } catch (error) {

    messageType.value = "error";

    message.value =
      error instanceof Error
        ? error.message
        : "本地文献列表加载失败";

  } finally {

    loading.value = false;

  }

}

function onCheckboxChange(
  event: Event,
  id: string
) {

  toggleDocument(
    id,
    (event.target as HTMLInputElement).checked
  );

}

function toggleDocument(
  id: string,
  checked: boolean
) {

  const next = new Set(props.selectedIds);

  if (checked) {

    if (next.size >= 20) {

      messageType.value = "error";

      message.value =
        "一次研究最多选择 20 篇文献";

      return;

    }

    next.add(id);

  } else {

    next.delete(id);

  }

  emit(
    "update:selectedIds",
    [...next]
  );

  message.value = "";

}

async function handleFiles(event: Event) {

  const input = event.target as HTMLInputElement;

  const files = Array.from(
    input.files || []
  );

  input.value = "";

  if (!files.length) return;

  uploading.value = true;

  message.value = "";

  const imported: string[] = [];

  const importedIds: string[] = [];

  const failures: string[] = [];

  try {

    for (const file of files) {

      if (file.size > 25 * 1024 * 1024) {

        failures.push(
          `${file.name}：超过 25 MB`
        );

        continue;

      }

      const data = new FormData();

      data.append("file", file);

      try {

        const response = await fetch(
          `${apiBase}/documents`,
          {
            method: "POST",
            body: data
          }
        );

        const payload = await response.json().catch(
          () => null
        );

        if (!response.ok) {

          const detail = payload?.detail;

          const reason =
            typeof detail === "string"
              ? detail
              : detail?.message ||
                `导入失败 (${response.status})`;

          failures.push(
            `${file.name}：${reason}`
          );

          continue;

        }

        imported.push(file.name);

        if (typeof payload?.id === "string") {
          importedIds.push(payload.id);
        }

      } catch (error) {

        failures.push(
          `${file.name}：${
            error instanceof Error
              ? error.message
              : "网络错误"
          }`
        );

      }

    }

    if (importedIds.length) {

      const selectedSet = new Set([
        ...props.selectedIds,
        ...importedIds
      ]);

      const selected = [
        ...selectedSet
      ].slice(0, 20);

      emit(
        "update:selectedIds",
        selected
      );

      if (selectedSet.size > 20) {

        failures.push(
          "单次研究最多选择 20 篇文献，超出部分已保留在资料库中"
        );

      }

    }

    await loadDocuments();

    messageType.value = failures.length
      ? "error"
      : "success";

    message.value = [
      imported.length
        ? `成功导入 ${imported.length} 个文件：${imported.join("、")}`
        : "",
      ...failures
    ].filter(Boolean).join("；");

  } finally {

    uploading.value = false;

  }

}

async function removeDocument(
  doc: LocalDocument
) {

  if (
    !window.confirm(
      `确定从本地资料库删除“${doc.title}”吗？`
    )
  ) {
    return;
  }

  try {

    await api(
      `/documents/${doc.id}`,
      {
        method: "DELETE"
      }
    );

    emit(
      "update:selectedIds",
      props.selectedIds.filter(
        id => id !== doc.id
      )
    );

    await loadDocuments();

    messageType.value = "success";

    message.value = `已删除：${doc.title}`;

  } catch (error) {

    messageType.value = "error";

    message.value =
      error instanceof Error
        ? error.message
        : "删除失败";

  }

}

onMounted(loadDocuments);

</script>

<style scoped>

.local-library {
  margin: 14px 0 4px;
  padding: 13px 14px;
  border: 1px solid #dfe7f3;
  border-radius: 12px;
  background: #fbfdff;
  min-width: 0;
}

.library-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.library-heading > div {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #263b5a;
  font-size: 13px;
}

.library-count {
  font-size: 11px;
  color: #6c7d96;
  background: #edf2fa;
  border-radius: 99px;
  padding: 2px 7px;
}

.upload-button {
  flex-shrink: 0;
  border: 1px solid #cbdaf0;
  border-radius: 8px;
  background: #fff;
  color: #3267ad;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}

.upload-button:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.library-hint {
  font-size: 11px;
  line-height: 1.55;
  color: #8290a5;
  margin: 7px 0 9px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0,0,0,0);
  white-space: nowrap;
  border: 0;
}

.library-state,
.library-empty {
  font-size: 12px;
  color: #8996a8;
  padding: 12px 4px;
  display: flex;
  align-items: center;
  gap: 9px;
}

.empty-icon {
  font-size: 20px;
  color: #a7b7cd;
}

.document-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  max-height: 190px;
  overflow: auto;
  padding-right: 2px;
}

.document-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}

.document-row.selected {
  background: #f0f6ff;
  border-color: #c9dcf8;
}

.document-row input {
  accent-color: #3979ce;
  flex-shrink: 0;
}

.file-type {
  width: 38px;
  flex-shrink: 0;
  text-align: center;
  padding: 4px 2px;
  border-radius: 5px;
  background: #eef2f8;
  color: #5b6e89;
  font-size: 9px;
  font-weight: 700;
}

.document-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.document-meta strong {
  font-size: 11px;
  color: #34445f;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.document-meta small {
  font-size: 10px;
  color: #8a97aa;
}

.icon-button {
  border: 0;
  background: transparent;
  color: #96a2b3;
  font-size: 18px;
  line-height: 1;
  padding: 3px 5px;
  cursor: pointer;
}

.icon-button:hover {
  color: #c34352;
}

.icon-button:disabled {
  opacity: .4;
  cursor: not-allowed;
}

.selection-footer {
  margin-top: 8px;
  font-size: 11px;
  color: #3972ba;
}

.library-message {
  font-size: 11px;
  line-height: 1.5;
  color: #287b57;
  margin: 8px 0 0;
  overflow-wrap: anywhere;
}

.library-message.error {
  color: #b54745;
}

</style>