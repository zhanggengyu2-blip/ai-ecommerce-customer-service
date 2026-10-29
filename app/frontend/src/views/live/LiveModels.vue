<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus/es/components/message/index.mjs';
import Icon from '../../features/workbench/components/WorkbenchIcon.vue';
import PreviewSelect from '../../features/preview/components/PreviewSelect.vue';
import { staffApi as api } from '../../features/live/api';
import type { Operation } from '../../features/live/knowledgeTypes';
type RoleName='dialogue'|'embedding'|'rerank';
interface ModelRole {provider:string;model_id:string;dimension:number|null;has_key:boolean;key_hint:string;verified:boolean;verified_at:string|null;api_key:string}
interface Configuration {version:number;models:Record<RoleName,ModelRole>;catalog:Record<RoleName,Record<string,string[]>>;preparing:boolean;operation:Operation|null}
const emit=defineEmits<{updated:[]}>();
const roles=[{id:'dialogue',name:'对话推理',description:'理解诉求、选择知识并生成回复',icon:'ChatLineRound'},
  {id:'embedding',name:'向量化',description:'将问题和知识转换为检索向量',icon:'Reading'},
  {id:'rerank',name:'重排序',description:'比较问题与候选知识的相关程度',icon:'Connection'}] as const;
const configuration=ref<Configuration|null>(null),form=reactive<Record<string,ModelRole>>({});
const version=ref(0),loading=ref(true),busy=ref(false),error=ref(''),checking=ref(''),checked=reactive<Record<string,boolean>>({});
const reception=reactive({enabled:false,version:0}),rag=reactive({version:0,final_top_k:5,min_score:.30});
let timer:ReturnType<typeof setInterval>|undefined,disposed=false;
const preparing=computed(()=>!!configuration.value?.preparing);
function payload(role:RoleName){const row=form[role];return {provider:row.provider,model_id:row.model_id,dimension:role==='embedding'?row.dimension:null,api_key:row.api_key};}
function changed(role:RoleName){checked[role]=false;}
function providerChanged(role:RoleName){const row=form[role];row.model_id=Object.values(configuration.value?.catalog[role][row.provider]||[])[0]||'';row.api_key='';changed(role);}
function hasExistingKey(role:RoleName){return form[role].provider===configuration.value?.models[role].provider && configuration.value?.models[role].has_key;}
async function load(){
 try{const [value,enabled,retrieval]=await Promise.all([api<Configuration>('/api/admin/settings/models'),api<typeof reception>('/api/admin/settings/reception'),api<typeof rag>('/api/admin/settings/retrieval')]);
  if(disposed)return;configuration.value=value;version.value=value.version;Object.assign(reception,enabled);Object.assign(rag,retrieval);
  roles.forEach(r=>{form[r.id]={...value.models[r.id],api_key:''};checked[r.id]=value.models[r.id].verified;});error.value='';
 }catch(e){if(!disposed)error.value=(e as Error).message;}finally{loading.value=false;}
}
async function save(){if(busy.value||preparing.value)return;busy.value=true;error.value='';
 try{const value=await api<{preparing:boolean}>('/api/admin/settings/models',{expected_version:version.value,...Object.fromEntries(roles.map(r=>[r.id,payload(r.id)]))},'PUT');
  roles.forEach(r=>form[r.id].api_key='');await load();ElMessage.success(value.preparing?'正在准备新检索内容，完成后自动生效':'模型配置已保存并校验');emit('updated');
 }catch(e){error.value=(e as Error).message;}finally{busy.value=false;}}
async function check(role:RoleName){if(checking.value||busy.value)return;checking.value=role;checked[role]=false;error.value='';
 try{await api('/api/admin/settings/models/check',{role,config:payload(role)});checked[role]=true;ElMessage.success('模型服务连接与返回校验通过');}
 catch(e){error.value=(e as Error).message;}finally{checking.value='';}}
async function enable(value:boolean|string|number){if(busy.value)return;busy.value=true;error.value='';
 try{Object.assign(reception,await api('/api/admin/settings/reception',{enabled:!!value,expected_version:reception.version},'PUT'));emit('updated');ElMessage.success(reception.enabled?'AI 自动接待已开启':'AI 自动接待已关闭，人工接待继续保留');}
 catch(e){error.value=(e as Error).message;}finally{busy.value=false;}}
async function saveRetrieval(){if(busy.value)return;busy.value=true;error.value='';
 try{if(!Number.isInteger(rag.final_top_k)||rag.final_top_k<1||rag.final_top_k>10||typeof rag.min_score!=='number'||!Number.isFinite(rag.min_score)||rag.min_score<0||rag.min_score>1)throw new Error('Top K 为 1–10 的整数，Score 为 0–1 的数值。');
  Object.assign(rag,await api('/api/admin/settings/retrieval',{expected_version:rag.version,final_top_k:rag.final_top_k,min_score:rag.min_score},'PUT'));ElMessage.success('检索设置已保存');}
 catch(e){error.value=(e as Error).message;}finally{busy.value=false;}}
onMounted(async()=>{await load();timer=setInterval(async()=>{if(preparing.value&&!busy.value){const value=await api<Configuration>('/api/admin/settings/models').catch(()=>null);if(value&&!disposed){configuration.value=value;if(!value.preparing){await load();emit('updated');}}}},2000);});
onUnmounted(()=>{disposed=true;clearInterval(timer);});
</script>
<template><div class="pv-page live-page"><div class="live-page-heading"><div><h1>AI 模型配置</h1><p>配置 AI 回复与知识检索所需的模型，全店客服共用。</p></div></div><p v-if="loading" class="live-muted">正在读取配置…</p><template v-if="configuration&&!loading">
<section class="pv-card pv-service-card"><div class="pv-service-icon"><Icon name="MagicStick"/></div><div><h3>AI 自动接待</h3><p>开启后自动回复新咨询；客服接入后由人工继续处理。</p></div><el-switch :model-value="reception.enabled" :disabled="busy||preparing" aria-label="AI 自动接待" @change="enable"/></section>
<div v-if="preparing" class="pv-notice"><Icon name="Loading" spin/><span>正在准备新的知识向量，完成后自动切换。当前可用配置继续提供服务。</span></div>
<p v-if="configuration.operation?.status==='FAILED'" class="live-error" role="alert">{{configuration.operation.error}}</p>
<form class="pv-card pv-model-settings" @submit.prevent="save"><div class="pv-panel-heading"><span class="pv-panel-meta">{{reception.enabled?'API Key 可以共用，也可以分别填写。':'完成三个模型配置并发布有效知识后，即可开启自动接待。'}}</span><button class="wb-btn primary" :disabled="busy||preparing||!!checking" type="submit">{{busy?'正在校验并保存…':'保存配置'}}</button></div>
<div class="pv-model-grid"><section v-for="role in roles" :key="role.id" class="pv-card pv-model-card"><div class="pv-model-heading"><span class="pv-model-symbol"><Icon :name="role.icon"/></span><div><h3>{{role.name}}</h3><p>{{role.description}}</p></div><span class="pv-tag" :class="configuration.models[role.id].verified?'green':'amber'">{{configuration.models[role.id].verified?'已配置':'待配置'}}</span></div>
<div class="pv-form"><label>服务商<PreviewSelect v-model="form[role.id].provider" :aria-label="`${role.name}服务商`" :disabled="busy||preparing" @change="providerChanged(role.id)"><option v-for="(_,provider) in configuration.catalog[role.id]" :key="provider" :value="provider">{{provider==='deepseek'?'DeepSeek':'百炼千问'}}</option></PreviewSelect></label>
<label>模型<PreviewSelect v-model="form[role.id].model_id" :aria-label="`${role.name}模型`" :disabled="busy||preparing" @change="changed(role.id)"><option v-for="model in configuration.catalog[role.id][form[role.id].provider]" :key="model">{{model}}</option></PreviewSelect></label>
<label v-if="role.id==='embedding'">向量维度<PreviewSelect :model-value="form.embedding.dimension ?? 1024" @update:model-value="form.embedding.dimension=Number($event)" aria-label="向量维度" :disabled="busy||preparing" @change="changed(role.id)"><option v-for="dimension in [64,128,256,512,768,1024,...(form.embedding.model_id==='text-embedding-v4'?[1536,2048]:[])]" :key="dimension" :value="dimension">{{dimension}}</option></PreviewSelect></label>
<label>API Key<input v-model="form[role.id].api_key" type="password" :aria-label="`${role.name} API Key`" autocomplete="new-password" :disabled="busy||preparing" :placeholder="hasExistingKey(role.id)?`已配置 · •••• ${configuration.models[role.id].key_hint}（留空保持）`:'填写当前服务商的 Key'" @input="changed(role.id)"/><small>仅在替换时填写；更换服务商需填写对应 Key。</small></label>
<div class="pv-model-check"><button class="wb-btn" type="button" :disabled="busy||preparing||!!checking" @click="check(role.id)"><Icon :name="checking===role.id?'Loading':'Connection'" :spin="checking===role.id"/>{{checking===role.id?'正在校验':'检查配置'}}</button><span v-if="checked[role.id]" class="pv-positive">真实调用已通过</span></div></div></section></div></form>
<section class="pv-card live-retrieval-settings"><div class="pv-panel-heading"><div><h3>检索设置</h3><p class="live-muted">重排分数达到 Score 阈值后，最多选取 Top K 个知识片段。</p></div><button class="wb-btn" :disabled="busy" @click="saveRetrieval">保存检索设置</button></div><div class="pv-form-grid pv-form"><label>Top K<input v-model.number="rag.final_top_k" aria-label="Top K" type="number" min="1" max="10" step="1" required/></label><label>Score<input v-model.number="rag.min_score" aria-label="Score" type="number" min="0" max="1" step="0.01" required/></label></div></section>
</template><p v-if="error" class="live-error" role="alert">{{error}}</p></div></template>
