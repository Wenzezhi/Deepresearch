<template>
  <section class="model-panel" aria-label="模型配置">
    <header><div><span class="eyebrow">模型服务</span><h2>模型配置</h2></div><button type="button" @click="requestSelect('')" :disabled="busy">＋ 新增</button></header>
    <label>已保存配置<select :disabled="busy" aria-label="编辑模型配置" :value="editingId" @change="selectEdit"><option value="">新增配置</option><option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
    <div class="config-actions"><button type="button" @click="editable=true; message=''" :disabled="busy || !editingId || editable"><UiIcon name="edit"/>修改</button><button class="trash-button" type="button" aria-label="删除当前模型配置" title="删除配置" @click="requestDelete" :disabled="busy || !editingId"><UiIcon name="trash"/></button></div>
    <form @submit.prevent="save"><fieldset :disabled="busy || !editable">
      <label>配置名称<input aria-label="配置名称" v-model="draft.name" required maxlength="80" placeholder="例如：DeepSeek · 日常研究" /></label>
      <label>API 地址<input aria-label="API 地址" v-model="draft.base_url" required type="url" placeholder="https://api.example.com/v1" /></label>
      <label>模型 ID<input aria-label="模型 ID" v-model="draft.model_id" required placeholder="服务商提供的模型 ID" /></label>
      <label>API Key<input aria-label="API Key" v-model="draft.api_key" type="password" autocomplete="new-password" :placeholder="existingKey ? '已保存，留空保持原密钥' : '本地免密服务可留空'" /></label>
      <div class="columns"><label>最大输出长度<input aria-label="最大输出长度" v-model.number="draft.max_tokens" type="number" min="1" max="1048576" required /></label><label>超时时间（秒）<input aria-label="超时时间" v-model.number="draft.timeout" type="number" min="1" max="600" required /></label></div>
      </fieldset>
      <p class="tip">点击“修改”后编辑已有配置；新增配置可直接填写。</p>
      <p class="tip">兼容 OpenAI 聊天接口的模型服务。密钥由本机后端保存。</p>
      <p v-if="message" role="status" :class="['message',{bad:failed}]">{{ message }}</p>
      <div class="actions"><button v-if="editingId && editable" type="button" @click="edit(profiles.find(p=>p.id===editingId)||null)" :disabled="busy">取消修改</button><button type="button" @click="test" :disabled="busy || !editingId">测试连接</button><button class="primary" :disabled="busy || !editable">{{ busy ? '处理中…' : '保存配置' }}</button></div>
    </form>
    <Teleport to="body"><dialog ref="deleteDialog" class="delete-dialog" aria-labelledby="delete-config-title" @click="dismissBackdrop"><h3 id="delete-config-title">删除模型配置</h3><p>确定要删除“{{ deleteTarget?.name }}”这条配置吗？</p><p class="tip">已有研究历史不会删除。</p><div class="dialog-actions"><button class="confirm-delete" type="button" @click="remove">是，删除</button><button class="keep-config" type="button" autofocus @click="deleteDialog?.close()">否，保留</button></div></dialog></Teleport>
    <Teleport to="body"><dialog ref="switchDialog" class="delete-dialog" aria-labelledby="switch-config-title" @cancel="pendingSelection=null"><h3 id="switch-config-title">配置尚未保存</h3><p>切换后将放弃当前未保存的修改。是否继续？</p><div class="dialog-actions"><button class="confirm-delete" type="button" @click="confirmSwitch">放弃修改并切换</button><button class="keep-config" type="button" autofocus @click="cancelSwitch">保留修改</button></div></dialog></Teleport>
  </section>
</template>
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import UiIcon from './UiIcon.vue';
import { api, type ModelProfile } from '../services/api';
const props = defineProps<{profiles: ModelProfile[];selectedId?:string}>();
const emit = defineEmits<{changed: [id?: string];select:[id:string]}>();
const editable=ref(true);
const deleteDialog=ref<HTMLDialogElement|null>(null);
const deleteTarget=ref<{id:string;name:string}|null>(null);
const editingId = ref(''); const existingKey = ref(false); const busy = ref(false); const message = ref(''); const failed = ref(false);
const defaults = () => ({name:'',base_url:'',model_id:'',api_key:'',max_tokens:8192,timeout:120});
const draft = reactive(defaults());
const baseline=ref(JSON.stringify(defaults()));
const dirty=computed(()=>editable.value && JSON.stringify(draft)!==baseline.value);
const switchDialog=ref<HTMLDialogElement|null>(null);const pendingSelection=ref<string|null>(null);
function activate(id:string){const p=props.profiles.find(p=>p.id===id)||null;edit(p);if(p)emit('select',p.id);}
function requestSelect(id:string){if(busy.value)return;if(id===editingId.value)return;if(dirty.value){pendingSelection.value=id;switchDialog.value?.showModal();return;}activate(id);}
function cancelSwitch(){pendingSelection.value=null;switchDialog.value?.close();}
function confirmSwitch(){const id=pendingSelection.value;cancelSwitch();if(id!==null)activate(id);}
defineExpose({requestSelect});
let initialized = false;
watch(() => [props.selectedId,props.profiles] as const, ([id,list]) => { if (!initialized && list.length) { edit(list.find(p=>p.id===id)||list[0]); initialized=true; } else if(id && id!==editingId.value && !dirty.value && !editable.value){edit(list.find(p=>p.id===id)||null);} }, {immediate:true});
function edit(p: ModelProfile | null) { editable.value=!p; editingId.value=p?.id || ''; existingKey.value=!!p?.has_api_key; Object.assign(draft,defaults(),p ? {name:p.name,base_url:p.base_url,model_id:p.model_id,max_tokens:p.max_tokens,timeout:p.timeout} : {}); message.value=''; baseline.value=JSON.stringify(draft); }
function selectEdit(e: Event) { const element=e.target as HTMLSelectElement;const id=element.value;element.value=editingId.value;requestSelect(id); }
async function action(fn: () => Promise<void>) { busy.value=true; message.value=''; failed.value=false; try {await fn();} catch(e){failed.value=true;message.value=e instanceof Error?e.message:'操作失败';} finally {busy.value=false;} }
async function save() { if(!editable.value)return; await action(async()=> { const p=await api<ModelProfile>(`/model-profiles${editingId.value?'/'+editingId.value:''}`,{method:editingId.value?'PUT':'POST',body:JSON.stringify(draft)});edit(p); message.value='配置已保存';emit('changed',p.id); }); }
function requestDelete(){if(!editingId.value)return;deleteTarget.value={id:editingId.value,name:props.profiles.find(p=>p.id===editingId.value)?.name||draft.name};deleteDialog.value?.showModal();}
function dismissBackdrop(e:MouseEvent){if(e.target===deleteDialog.value)deleteDialog.value?.close();}
async function remove(){const id=deleteTarget.value?.id;if(!id)return;deleteDialog.value?.close();await action(async()=>{await api(`/model-profiles/${id}`,{method:'DELETE'});edit(props.profiles.find(p=>p.id!==id)||null);emit('select',editingId.value);emit('changed');message.value='配置已删除';});}
async function test() { await action(async()=>{ const current=props.profiles.find(p=>p.id===editingId.value); if (!current || draft.api_key || draft.base_url!==current.base_url || draft.model_id!==current.model_id || draft.max_tokens!==current.max_tokens || draft.timeout!==current.timeout) {failed.value=true;message.value='请先保存修改，再测试连接';return;} const r=await api<{ok:boolean;message:string}>(`/model-profiles/${editingId.value}/test`,{method:'POST'});failed.value=!r.ok;message.value=r.message;}); }
</script>
<style scoped>
.model-panel{background:#fff;border:1px solid #e1e8f4;border-radius:20px;padding:26px;align-self:start;color:#243047;min-width:0}.model-panel header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.model-panel h2{font-size:21px;margin:4px 0}.eyebrow,.tip{font-size:12px;color:#7b8aa4}label{display:flex;flex-direction:column;gap:8px;font-size:13px;font-weight:600;margin-bottom:16px}input,select{box-sizing:border-box;width:100%;min-width:0;border:1px solid #d5deed;border-radius:9px;padding:11px;background:#fbfcff;color:#243047;font:inherit}.columns{display:grid;grid-template-columns:1fr 1fr;gap:14px}.actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;margin-top:20px}button{border:1px solid #d5deed;border-radius:8px;padding:9px 12px;background:white;cursor:pointer;color:#41516e}button:disabled{opacity:.5;cursor:wait}.primary{background:#3974ff;color:white;border:0}.danger{color:#be3448;margin-right:auto}.message{font-size:13px;color:#16704a}.bad{color:#b42338}
</style>

<style scoped>
fieldset{border:0;padding:0;margin:0;min-width:0}fieldset:disabled input{background:#f2f5fa;color:#5d6c85;cursor:default;opacity:1}.config-actions{display:flex;justify-content:flex-end;gap:8px;margin:-4px 0 18px}.config-actions button{display:inline-flex;align-items:center;gap:6px}.trash-button:hover:enabled{color:#c42d3b;background:#fff2f3;border-color:#f3bdc5}.delete-dialog{border:1px solid #e0e6f1;border-radius:18px;padding:26px;max-width:440px;width:calc(100% - 40px);color:#27344e;box-shadow:0 24px 80px #1a2a4b30}.delete-dialog::backdrop{background:#1f2a443d;backdrop-filter:blur(3px)}.delete-dialog h3{margin:0 0 18px}.delete-dialog p{line-height:1.7;overflow-wrap:anywhere}.dialog-actions{display:flex;gap:12px;margin-top:24px}.dialog-actions button{flex:1;padding:12px;border:0;font-weight:600;color:white}.dialog-actions .confirm-delete{background:#dc3545}.dialog-actions .keep-config{background:#168559}.dialog-actions button:focus-visible{outline:3px solid #94c9b5;outline-offset:3px}
</style>

