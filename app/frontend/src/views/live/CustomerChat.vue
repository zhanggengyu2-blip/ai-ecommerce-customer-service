<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import { createApi, readMessages, type Reception, type StoredMessage } from '../../features/live/api';
import { timeOf } from '../../features/workbench/types';
import '../../features/workbench/workbench.css';
import '../../features/preview/color-theme.css';
import './live.css';
const entry = new URLSearchParams(location.search).get('store') || '';
const token = ref<string|null>(null), thread = ref<number|null>(null), conversation = ref<Reception|null>(null);
const messages = ref<StoredMessage[]>([]), text = ref(''), error = ref(''), busy = ref(false), loading = ref(true);
const timeline = ref<HTMLElement|null>(null);
const api = createApi(() => token.value);
let timer: ReturnType<typeof setInterval> | undefined, disposed = false, refreshing = false, version = 0;
let pending: {key: string; content: string} | null = null;
const status = computed(() => conversation.value?.status === 'HUMAN_ACTIVE' ? `${conversation.value.agent_name}正在为您服务` : conversation.value?.status === 'AI_ACTIVE' ? 'AI 客服正在为您服务' : conversation.value?.status === 'CLOSED' ? '本次沟通已结束，可继续发送新的问题' : messages.value.length ? '消息已接收，等待客服接入' : '欢迎咨询，请留下您的问题');
async function scroll() { await nextTick(); if(timeline.value) timeline.value.scrollTop = timeline.value.scrollHeight; }
async function initialize() {
  if (busy.value) return; busy.value = true; loading.value = true; error.value = '';
  try {
    const key = `foundation-visitor:${entry}`;
    const previous = localStorage.getItem(key);
    const visitor = previous ? JSON.parse(previous) : {visitor_id: crypto.randomUUID(), visitor_proof: crypto.randomUUID()};
    localStorage.setItem(key, JSON.stringify(visitor));
    const result = await api<{access_token: string; visitor_proof: string}>('/api/auth/guest-session', {entry_code: entry, ...visitor});
    visitor.visitor_proof = result.visitor_proof; localStorage.setItem(key, JSON.stringify(visitor)); token.value = result.access_token;
    const chat = await api<{thread_id:number; conversation:Reception}>('/api/customer/chat', {});
    thread.value = chat.thread_id; conversation.value = chat.conversation;
    messages.value = await readMessages(api, `/api/customer/threads/${thread.value}/messages`); await scroll();
    if (!disposed && !timer) timer = setInterval(() => { if (!busy.value) void refresh(); }, 3000);
  } catch(e) { error.value = (e as Error).message; } finally { loading.value = false; busy.value = false; }
}
async function refresh() {
  if (refreshing || !thread.value || disposed) return; refreshing = true; const generation = ++version;
  try {
    const chat = await api<{conversation: Reception}>(`/api/customer/threads/${thread.value}`);
    const items = await readMessages(api, `/api/customer/threads/${thread.value}/messages`, messages.value);
    if(generation !== version || disposed) return;
    const changed = items.length !== messages.value.length;
    conversation.value = chat.conversation; messages.value = items; error.value = '';
    if (changed) await scroll();
  } catch(e) { if(!disposed) error.value = (e as Error).message; } finally { refreshing = false; }
}
async function send() {
  if (busy.value || !thread.value || !text.value.trim()) return; busy.value = true; version++;
  const content = text.value.trim(); if (!pending || pending.content !== content) pending = {key: crypto.randomUUID(), content};
  try {
    const result = await api<{message:StoredMessage; conversation:Reception}>(`/api/customer/threads/${thread.value}/messages`, {client_message_id: pending.key, content});
    if (!messages.value.some(m => m.id === result.message.id)) messages.value.push(result.message);
    messages.value.sort((a,b) => a.id-b.id); conversation.value = result.conversation;
    text.value = ''; pending = null; error.value = ''; await scroll();
  } catch(e) { error.value = (e as Error).message; } finally { busy.value = false; }
}
async function handoff() {
  if(busy.value || !thread.value || !conversation.value)return;busy.value=true;version++;
  try{conversation.value=await api<Reception>(`/api/customer/threads/${thread.value}/handoff`,{conversation_id:conversation.value.id,expected_epoch:conversation.value.reception_epoch});error.value='';}
  catch(e){error.value=(e as Error).message;}finally{busy.value=false;}
}
async function end() {
  if(busy.value || !thread.value || !conversation.value) return; busy.value = true; version++;
  try { conversation.value = await api<Reception>(`/api/customer/threads/${thread.value}/end`, {conversation_id: conversation.value.id, expected_epoch: conversation.value.reception_epoch}); error.value = ''; }
  catch(e) { error.value = (e as Error).message; } finally { busy.value = false; }
}
onMounted(initialize); onUnmounted(() => { disposed = true; version++; clearInterval(timer); });
</script>
<template><div class="customer-shell"><section class="customer-chat"><header><span class="live-symbol">禾</span><div><h1>店铺客服</h1><p>{{loading?'正在连接…':status}}</p></div><button v-if="conversation?.status==='AI_ACTIVE'" class="wb-text-button" :disabled="busy" @click="handoff">转人工</button><button v-if="conversation && conversation.status !== 'CLOSED'" class="wb-text-button" :disabled="busy" @click="end">结束咨询</button></header><div ref="timeline" class="customer-messages" aria-label="聊天消息" aria-live="polite"><div v-if="!messages.length && !loading" class="customer-welcome"><h2>您好，有什么可以帮您？</h2><p>请留下您的问题，我们会在这里回复。</p></div><article v-for="message in messages" :key="message.id" class="customer-message" :class="{mine:message.sender_type==='CUSTOMER'}"><small>{{message.sender_type==='CUSTOMER'?'我':message.sender_name || '店铺客服'}} · {{timeOf(message.created_at)}}</small><p>{{message.content}}</p><details v-if="message.citations?.length" class="customer-sources"><summary>知识来源</summary><div v-for="source in message.citations" :key="source.id"><strong>{{source.document_title}}</strong><p>{{source.content}}</p></div></details></article></div><p v-if="error" class="live-error" role="alert">{{error}} <button :disabled="busy" @click="initialize">重新连接</button></p><form class="customer-composer" @submit.prevent="send"><textarea v-model="text" aria-label="发送给客服的消息" placeholder="输入您的问题…" maxlength="10000" rows="3" :disabled="busy || !thread" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" /><div><small>聊天记录会保留在此入口</small><button class="wb-btn primary" :disabled="busy || !thread || !text.trim()">{{busy?'正在处理…':'发送'}}</button></div></form></section></div></template>
