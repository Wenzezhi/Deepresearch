<template>
<section class="history" aria-label="研究历史">
  <header><h3>历史记录</h3><span>{{ runs.length }} 项</span></header>
  <input v-model="query" aria-label="搜索历史研究" placeholder="搜索历史研究" type="search" />
  <div class="history-scroll">
    <p v-if="!filtered.length" class="empty">{{ query ? '没有匹配的研究' : '暂无历史，开始你的第一项研究' }}</p>
    <template v-for="(run,i) in filtered" :key="run.id">
      <p v-if="i===0 || dateLabel(run)!==dateLabel(filtered[i-1])" class="date">{{ dateLabel(run) }}</p>
      <div :class="['history-row',{selected:run.id===selected}]">
        <button class="history-open" @click="$emit('open',run.id)"><strong>{{ run.title }}</strong><span><i :class="run.status">{{ labels[run.status] || run.status }}</i><small>{{ run.timings?.total !== undefined ? duration(run.timings.total) : run.profile?.name || '历史研究' }}</small></span></button>
        <details><summary :aria-label="`管理历史：${run.title}`">⋯</summary><div class="menu"><button @click="closeMenu($event); $emit('rename',run)">重命名</button><button :disabled="run.status==='running'" @click="closeMenu($event); $emit('delete',run)">删除</button></div></details>
      </div>
    </template>
  </div>
  <p class="local-hint">历史记录保存在本机</p>
</section>
</template>
<script setup lang="ts">
import {computed,ref} from 'vue';
import type {ResearchRun} from '../services/api';
const props=defineProps<{runs:ResearchRun[];selected?:string}>();
defineEmits<{open:[id:string];rename:[run:ResearchRun];delete:[run:ResearchRun]}>();
const query=ref('');const filtered=computed(()=>props.runs.filter(r=>(r.title+' '+r.topic).toLowerCase().includes(query.value.trim().toLowerCase())));
const labels:Record<string,string>={running:'运行中',paused:'已暂停',completed:'已完成',partial:'部分失败',failed:'失败',interrupted:'已中断'};
function duration(n:number){const s=Math.floor(n);return `${Math.floor(s/60)}`.padStart(2,'0')+':'+`${s%60}`.padStart(2,'0');}
function closeMenu(event:Event){(event.target as HTMLElement).closest('details')?.removeAttribute('open');}
function dateLabel(r:ResearchRun){const date=new Date(r.created_at); const today=new Date(); if(date.toDateString()===today.toDateString())return '今天';today.setDate(today.getDate()-1);if(date.toDateString()===today.toDateString())return '昨天';return date.toLocaleDateString('zh-CN');}
</script>
<style scoped>
.history{min-height:150px;display:flex;flex-direction:column;flex:1;gap:10px;min-width:0}.history header{display:flex;align-items:center;justify-content:space-between}.history h3{font-size:14px;margin:0;color:#33425e}.history header span,.local-hint,.empty{font-size:12px;color:#8a97ad}.history input{width:100%;box-sizing:border-box;border:1px solid #dbe4f1;border-radius:9px;padding:10px;background:#fff;color:#243047}.history-scroll{overflow-y:auto;flex:1;min-height:70px}.date{font-size:12px;color:#71809b;margin:10px 4px}.history-row{position:relative;display:flex;align-items:flex-start;margin:5px 0;border:1px solid transparent;border-radius:10px;padding:9px 8px;gap:5px}.history-row:hover{background:#f6f8ff}.selected{background:#eaf1ff!important;border-color:#c9d9ff}.history-open{flex:1;min-width:0;text-align:left;background:none;border:0;color:#283650;cursor:pointer;padding:0}.history-open strong{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px;line-height:1.8;font-weight:500}.history-open span{display:flex;align-items:center;gap:7px;margin-top:5px}.history-open small{font-size:11px;color:#7a89a4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.history-open i{font-style:normal;font-size:11px;border-radius:4px;background:#edf0f5;color:#61708a;padding:2px 5px;white-space:nowrap}.history-open i.completed{background:#dff5eb;color:#178253}.history-open i.running{background:#e0eaff;color:#396dd6}.history-open i.failed,.history-open i.partial{background:#fff0ed;color:#c55043}summary{cursor:pointer;list-style:none;color:#7c8aa0}.menu{position:absolute;right:6px;top:32px;z-index:5;box-shadow:0 4px 20px #172a4420;border:1px solid #e1e8f4;border-radius:8px;background:white;padding:5px}.menu button{display:block;border:0;background:white;padding:7px 14px;color:#475877;cursor:pointer;width:100%}.menu button:disabled{opacity:.4}.local-hint{margin:0;padding-top:3px}
</style>
