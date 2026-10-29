<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref } from 'vue';
import { ElMessage } from 'element-plus/es/components/message/index.mjs';
import WorkbenchPage from '../support/WorkbenchPage.vue';
import LiveModels from './LiveModels.vue';
import LiveKnowledge from './LiveKnowledge.vue';
import LiveRecall from './LiveRecall.vue';
import LiveTraces from './LiveTraces.vue';
import '../../features/preview/preview.css';
import MessageTimeline from '../../features/workbench/components/MessageTimeline.vue';
import { useWorkbench, WorkbenchKey } from '../../features/workbench/useWorkbench';
import { createLiveRepository, messageView } from '../../features/live/repository';
import { allPages, readMessages, staffApi as api, type Reception, type Staff } from '../../features/live/api';
import { dateOf, type WorkbenchMessage } from '../../features/workbench/types';
const emit = defineEmits<{logout: []}>();
const wb = useWorkbench({ repository: createLiveRepository(), live: true, pollMs: 3000 }); provide(WorkbenchKey, wb);
const store = ref<{name: string; entry_code: string; capabilities?:{reception_enabled:boolean}} | null>(null), error = ref('');
const navigation=[{id:'workbench',title:'会话工作台'},{id:'models',title:'模型配置'},{id:'knowledge',title:'知识管理'},{id:'recall',title:'召回测试'},{id:'traces',title:'调用记录'}];
const hash=ref(window.location.hash);
function hashChanged(){hash.value=window.location.hash;}
window.addEventListener('hashchange',hashChanged);
const page=computed(()=>{const key=hash.value.replace(/^#\/?/,'').split('/')[0];return navigation.some(n=>n.id===key)?key:'workbench';});
const traceId=computed(()=>page.value==='traces'?hash.value.replace(/^#\/?/,'').split('/')[1]||'':'');
function navigate(id:string){window.location.hash=id;}
async function refreshStore(){try{store.value=await api('/api/admin/store');}catch(e){error.value=(e as Error).message;}}
const settingsOpen = ref(false), users = ref<Staff[]>([]), settingsBusy = ref(false);
const username = ref(''), displayName = ref(''), password = ref('');
const historyOpen = ref(false), history = ref<Reception[]>([]), record = ref<Reception|null>(null), recordMessages = ref<WorkbenchMessage[]>([]);
let heartbeat: ReturnType<typeof setInterval> | undefined, disposed = false;
let historyVersion = 0;
async function beat() { try { await api('/api/agent/heartbeat', {}); if (!disposed) error.value = ''; } catch(e) { if (!disposed) error.value = (e as Error).message; } }
onMounted(async () => {
  try { store.value = await api('/api/admin/store'); } catch(e) { error.value = (e as Error).message; }
  if (disposed) return;
  await beat(); if (!disposed) heartbeat = setInterval(beat, 10000);
});
onUnmounted(() => { disposed = true; clearInterval(heartbeat); window.removeEventListener('hashchange',hashChanged); });
async function logout() { try { await api('/api/auth/logout', {}); emit('logout'); } catch(e) { error.value = (e as Error).message; } }
async function openSettings() { settingsOpen.value = true; try { users.value = await allPages(api, '/api/admin/users/page'); } catch(e) { ElMessage.warning((e as Error).message); } }
async function createStaff() {
  if (settingsBusy.value) return; settingsBusy.value = true;
  try { await api('/api/admin/users', {username: username.value, display_name: displayName.value, password: password.value}); username.value = ''; displayName.value = ''; password.value = ''; await openSettings(); ElMessage.success('客服账号已创建'); }
  catch(e) { ElMessage.warning((e as Error).message); } finally { settingsBusy.value = false; }
}
async function toggle(user: Staff) {
  if(settingsBusy.value) return; settingsBusy.value = true;
  try { await api(`/api/admin/users/${user.id}`, {active: !user.active}, 'PATCH'); await openSettings(); }
  catch(e) { ElMessage.warning((e as Error).message); } finally { settingsBusy.value = false; }
}
async function openHistory() {
  historyOpen.value = true; record.value = null; recordMessages.value = []; historyVersion++;
  try { history.value = await allPages(api, '/api/admin/conversations'); } catch(e) { ElMessage.warning((e as Error).message); }
}
async function viewRecord(c: Reception) {
  record.value = c; recordMessages.value = []; const version = ++historyVersion;
  try { const messages = await readMessages(api, `/api/admin/conversations/${c.id}/messages`); if(version === historyVersion) recordMessages.value = messages.map(messageView); }
  catch(e) { ElMessage.warning((e as Error).message); }
}
</script>
<template><div class="live-workspace"><header class="live-header"><a class="live-logo" href="?mode=live"><span class="live-symbol">禾</span><strong>{{store?.name || '客服工作台'}}</strong><small>{{navigation.find(n=>n.id===page)?.title}}</small></a><div class="live-header-actions"><a v-if="store" class="wb-text-button" :href="`?mode=customer&store=${store.entry_code}`" target="_blank" rel="noopener">客户聊天入口 ↗</a><button class="wb-text-button" @click="openHistory">历史会话</button><button class="wb-text-button" @click="openSettings">客服账号</button><button class="wb-btn" :disabled="wb.presenceBusy.value" @click="wb.setOnline(!wb.staff.online)"><i class="wb-dot" :class="{offline:!wb.staff.online}"></i>{{wb.staff.name}} · {{wb.staff.online?'在线':'离线'}}</button><button class="wb-text-button" @click="logout">退出</button></div></header><div v-if="error" class="live-error" role="alert">{{error}}</div><nav class="live-navigation" aria-label="客服与知识导航"><button v-for="item in navigation" :key="item.id" :class="{active:page===item.id}" :aria-current="page===item.id?'page':undefined" @click="navigate(item.id)">{{item.title}}</button><button class="live-ai-status" @click="navigate('models')"><i class="wb-dot" :class="{offline:!store?.capabilities?.reception_enabled}"></i>AI 接待{{store?.capabilities?.reception_enabled?'已开启':'已关闭'}}</button></nav><main class="live-content"><WorkbenchPage v-show="page==='workbench'" embedded/><LiveModels v-if="page==='models'" @updated="refreshStore"/><LiveKnowledge v-if="page==='knowledge'" @updated="refreshStore"/><LiveRecall v-if="page==='recall'"/><LiveTraces v-if="page==='traces'" :initial-id="traceId"/></main></div>
<el-drawer v-model="settingsOpen" title="客服账号" size="min(560px, 100vw)" class="wb-history-drawer"><p class="live-muted">本店客服共享会话和记录；停用账号会立即使该账号的登录失效。</p><div v-for="user in users" :key="user.id" class="live-user-row"><div><strong>{{user.display_name}}</strong><small>{{user.username}} · {{user.active?'使用中':'已停用'}}</small></div><button class="wb-btn" :disabled="user.id===wb.staff.id || settingsBusy" @click="toggle(user)">{{user.active?'停用':'启用'}}</button></div><form class="live-account-form" @submit.prevent="createStaff"><h3>新增客服</h3><label>客服名称<input v-model="displayName" required maxlength="80" /></label><label>登录账号<input v-model="username" required minlength="3" maxlength="100" autocomplete="off" /></label><label>初始密码<input v-model="password" type="password" required minlength="12" maxlength="128" autocomplete="new-password" placeholder="至少 12 位" /></label><button class="wb-btn primary" :disabled="settingsBusy">{{settingsBusy?'正在保存…':'创建账号'}}</button></form></el-drawer>
<el-drawer v-model="historyOpen" title="历史会话记录" size="min(900px, 100vw)" class="wb-history-drawer"><div class="live-history"><div><p v-if="!history.length" class="live-muted">还没有已完结的会话。</p><button v-for="c in history" :key="c.id" class="live-history-row" :class="{selected:record?.id===c.id}" @click="viewRecord(c)"><strong>{{c.customer_name}} · #{{c.id}}</strong><small>{{dateOf(c.closed_at || c.last_message_at)}} · {{c.agent_name || '尚未接入人工'}}</small><span>{{c.consultation_summary || '尚未生成摘要'}}</span></button></div><div v-if="record" class="live-record"><h3>会话 #{{record.id}}</h3><MessageTimeline :key="record.id" :messages="recordMessages" :orders="[]" :customer="record.customer_name" tone="blue" history /></div></div></el-drawer>
</template>
