<template>
<section class="timing-panel" aria-label="研究耗时">
  <header><h3>研究耗时</h3><button class="run-control" :class="run?.status==='running'?'running':run?.status==='completed'?'completed':'start'" :disabled="busy || !run || run.status==='completed'" @click="$emit('control')">{{ run?.status==='running'?'运行中':run?.status==='completed'?'已完成':'开始生成' }}</button></header>
  <div class="total"><span>总耗时</span><strong>{{ format(run?.timings?.total) }}</strong></div>
  <div v-if="expanded" class="timing-details">
  <div v-for="phase in phases" :key="phase.key" class="phase"><span><i :class="{active:run?.timing_active?.[phase.key]}"></i>{{ phase.label }}</span><b>{{ format(run?.timings?.[phase.key]) }}</b></div>
  <p class="timing-hint">并发阶段按实际经过时间统计</p>
  <section v-if="tasks.length"><h4>各子任务耗时</h4><div class="task-timings"><div v-for="task in tasks" :key="task.id"><strong>{{ task.title }}</strong><span>搜索 {{ format(run?.timings?.[`task:${task.id}:search`]) }} · 总结 {{ format(run?.timings?.[`task:${task.id}:summary`]) }}</span></div></div></section>
  <p v-if="run?.status==='interrupted'" class="timing-hint">中断耗时以最后保存的记录为准</p>
  <p v-if="run?.profile" class="model-caption" :title="run.profile.model_id">模型：{{ run.profile.name }}</p>
</div>
  <button class="timing-toggle" :aria-expanded="expanded" @click="expanded=!expanded">{{ expanded?"收起 ▴":"展开 ▾" }}</button>
</section>
</template>
<script setup lang="ts">
import {ref,watch} from 'vue';
import type {ResearchRun} from '../services/api';
const props=defineProps<{run:ResearchRun|null;tasks:{id:number;title:string}[];busy?:boolean}>();
defineEmits<{control:[]}>();
const expanded=ref(false);watch(()=>props.run?.id,()=>expanded.value=false);
const phases=[{key:'planning',label:'任务规划'},{key:'execution',label:'子任务执行'},{key:'report',label:'报告生成'}];
function format(value:number|undefined){if(value===undefined)return '—';const s=Math.max(0,Math.floor(value));const hours=Math.floor(s/3600);return (hours?`${hours}:`:'')+`${Math.floor(s/60)%60}`.padStart(2,'0')+':'+`${s%60}`.padStart(2,'0');}
</script>
<style scoped>
.timing-panel{background:#f8faff;border:1px solid #e1e8f5;border-radius:12px;padding:12px 14px;flex-shrink:0;color:#40516b}.timing-panel header{display:flex;justify-content:space-between;align-items:center}.timing-panel h3{margin:0;font-size:13px}.timing-panel header>span{font-size:11px;color:#8997ae}.total{display:flex;align-items:center;justify-content:space-between;padding:6px 0;font-size:12px}.total strong{font-size:22px;color:#315fca;font-variant-numeric:tabular-nums}.phase{display:flex;justify-content:space-between;padding:2px 0;font-size:12px}.phase span{display:flex;align-items:center;gap:7px}.phase b{font-weight:500;font-variant-numeric:tabular-nums}.phase i{height:5px;width:5px;background:#b9c6dc;border-radius:50%}.phase .active{background:#7265ee;box-shadow:0 0 0 3px #7265ee15}.timing-hint{font-size:10px;margin:8px 0 0;color:#8a98b0}.timing-panel summary{cursor:pointer;font-size:11px;margin-top:9px;color:#61789c}.task-timings{max-height:125px;overflow:auto}.task-timings>div{display:flex;flex-direction:column;gap:4px;font-size:11px;margin-top:9px}.task-timings strong{font-weight:500}.task-timings span{color:#7c8aa0}.model-caption{font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#7d8ca6;margin:9px 0 0}
</style>

<style scoped>.run-control{border:0;border-radius:6px;padding:4px 8px;font-size:12px;cursor:pointer}.running{background:#3578ff;color:white}.start{background:#e74d5e;color:white}.completed{background:#d9f4e6;color:#16835d;cursor:default}.run-control:disabled{cursor:default}</style>
<style scoped>.timing-toggle{display:block;width:100%;margin-top:6px;border:0;border-top:1px solid #e1e8f5;padding:8px 0 0;background:transparent;color:#426699;cursor:pointer;font-size:12px}.timing-details h4{font-size:12px;margin:12px 0 4px}</style>
