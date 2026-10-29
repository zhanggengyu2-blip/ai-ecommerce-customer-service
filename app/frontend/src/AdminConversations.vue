<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, type Conversation, type Message } from './api'
import { formatLocalDateTime } from './domain/datetime'
import { conversationStatusLabels, messageSenderLabels } from './domain/conversationLabels'
type AdminConversation = Conversation & { customer_name: string; customer_username: string; can_reply: boolean; account_name: string; platform_code: string }
const props = defineProps<{ token: string; view: string; readonly: boolean; accountId?: number | null }>()
const emit = defineEmits<{ error: [error: unknown] }>()
const conversations = ref<AdminConversation[]>([]), current = ref<AdminConversation | null>(null), messages = ref<Message[]>([])
const draft = ref(''), busy = ref(false), filter = ref(''), errorState = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
const titles: Record<string, string> = { live: '实时会话', pending: '待处理', history: '历史会话', handoff: '转人工队列' }
const filtered = computed(() => conversations.value.filter(c => {
  const matchView = props.view === 'history' ? c.status === 'CLOSED' : ['pending','handoff'].includes(props.view) ? c.status === 'WAITING_USER' : ['AI_ACTIVE','HUMAN_ACTIVE'].includes(c.status)
  return matchView && (!filter.value || JSON.stringify(c).toLowerCase().includes(filter.value.toLowerCase()))
}))
async function load() {
  if (errorState.value || !props.token) return
  try {
    conversations.value = await api(`/api/admin/conversations${props.accountId ? `?account_id=${props.accountId}` : ''}`, 'GET', undefined, props.token)
    if (current.value) {
      const conversation = conversations.value.find(c => c.id === current.value?.id)
      if (conversation) current.value = conversation
      const selectedId = current.value.id
      const rows = await api<Message[]>(`/api/admin/conversations/${selectedId}/messages`, 'GET', undefined, props.token)
      if (current.value?.id === selectedId) messages.value = rows
    }
  } catch (error) { errorState.value = true; emit('error', error) }
}
async function select(row: AdminConversation) { current.value = row; await load() }
async function action(name: string, body?: unknown) {
  if (!current.value || busy.value) return
  busy.value = true
  try { await api(`/api/agent/conversations/${current.value.id}/${name}`, 'POST', body, props.token); if (name === 'messages') draft.value = ''; await load() }
  catch (error) { emit('error', error) } finally { busy.value = false }
}
watch(() => props.view, () => { current.value = null; messages.value = []; filter.value = ''; errorState.value = false; load() })
watch(() => props.accountId, () => { current.value = null; messages.value = []; load() })
onMounted(() => { load(); timer = setInterval(load, 5000) })
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <section>
    <div class="page-heading"><div><h2>{{ titles[view] }}</h2><p>每 5 秒刷新 · 显示最近 200 个会话 · {{ readonly ? '当前角色只读' : '先接管，再回复' }}</p></div><el-button @click="errorState = false; load()">刷新</el-button></div>
    <div class="admin-chat">
      <aside><el-input v-model="filter" clearable placeholder="搜索客户或会话" /><p class="muted">{{ filtered.length }} 个会话</p><button v-for="row in filtered" :key="row.id" class="conversation" :class="{selected:current?.id === row.id}" @click="select(row)"><strong>{{ row.customer_name || row.customer_username }} · #{{ row.id }}</strong><small>{{ row.platform_code }} · {{ row.account_name }} · {{ conversationStatusLabels[row.status] || row.status }}</small><span>{{ row.handoff_reason || '正常接待' }}</span></button><el-empty v-if="!filtered.length" description="暂无此类会话" :image-size="60" /></aside>
      <section class="thread"><div v-if="current" class="thread-head"><div><h2>{{ current.customer_name }} · 会话 #{{ current.id }}</h2><small>{{ current.platform_code }} · {{ current.account_name }} · {{ conversationStatusLabels[current.status] || current.status }}</small></div><div v-if="!readonly"><el-button v-if="current.status === 'WAITING_USER'" type="primary" :loading="busy" @click="action('claim')">接管</el-button><el-button v-if="current.can_reply" :disabled="busy" @click="action('close')">结束会话</el-button></div></div><div v-if="!current" class="empty">选择左侧会话查看消息</div><template v-else><div class="messages"><article v-for="message in messages" :key="message.id" class="bubble" :class="message.sender_type.toLowerCase()"><small>{{ messageSenderLabels[message.sender_type] || message.sender_type }} · {{ formatLocalDateTime(message.created_at) }}</small><p>{{ message.content }}</p><details v-if="message.citations?.length"><summary>知识来源</summary><div v-for="citation in message.citations" :key="citation.version_id">{{ citation.title }} · 版本 {{ citation.version_id }}</div></details></article></div><div v-if="!readonly && current.can_reply" class="composer"><el-input v-model="draft" type="textarea" placeholder="接管此会话后回复客户" :disabled="busy" /><el-button type="primary" :disabled="!draft.trim() || busy" @click="action('messages',{content:draft})">发送</el-button></div></template></section>
    </div>
  </section>
</template>
