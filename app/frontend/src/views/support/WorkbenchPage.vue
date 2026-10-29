<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue';
import { ElMessage } from 'element-plus/es/components/message/index.mjs';
import { useWorkbench, WorkbenchKey } from '../../features/workbench/useWorkbench';
import type { WorkbenchConversation, WorkbenchOrder, WorkbenchTicket } from '../../features/workbench/types';
import { dateOf, money, statusLabels, ticketTypeLabels, timeOf } from '../../features/workbench/types';
import Icon from '../../features/workbench/components/WorkbenchIcon.vue';
import ProductThumbnail from '../../features/workbench/components/ProductThumbnail.vue';
import MessageTimeline from '../../features/workbench/components/MessageTimeline.vue';
import OrderDetailDialog from '../../features/workbench/components/OrderDetailDialog.vue';
import TicketDialog from '../../features/workbench/components/TicketDialog.vue';
import '../../features/workbench/workbench.css';

defineProps<{ embedded?: boolean }>();
const context = inject(WorkbenchKey) || useWorkbench();
const { capabilities, loadError, refresh, conversations, current, selectedId, staff, loading, presenceBusy, actionBusy, composer, isOwner,
  select, toggleAssist, setOnline, claim, close, reopen, send, attach, incoming, saveTicket, generate } = context;
const search = ref('');
const filter = ref('all');
const mobileChat = ref(false), mobileRelated = ref(false);
const ordersExpanded = ref(false);
const selectedOrder = ref<WorkbenchOrder | null>(null), orderOpen = ref(false);
const ticketOpen = ref(false), chooseOrderOpen = ref(false);
const ticketConversation = ref<WorkbenchConversation | null>(null);
const ticketOrder = ref<WorkbenchOrder | null>(null), editingTicket = ref<WorkbenchTicket | null>(null);
const closeConfirm = ref(false), closingId = ref<number | null>(null);
const closingConversation = computed(() => conversations.value.find(c => c.id === closingId.value));
function requestClose() { if (current.value && isOwner.value) { closingId.value = current.value.id; closeConfirm.value = true; } }
async function confirmClose() { if (closingId.value === null) return; await close(closingId.value); closeConfirm.value = false; }
const historyOpen = ref(false), historyId = ref<number | null>(null);
const contacts = computed(() => {
  const latest = new Map<number, WorkbenchConversation>();
  for (const row of conversations.value) {
    const previous = latest.get(row.customerId);
    if (!previous || row.id > previous.id) latest.set(row.customerId, row);
  }
  return [...latest.values()];
});
const timeline = computed(() => {
  if (!current.value) return [];
  const messages = [...(current.value.timelineHistory || []), ...current.value.messages];
  return messages.filter((m,i) => messages.findIndex(x => x.id === m.id) === i);
});
const imageOpen = ref(false), imageUrl = ref('');
const emojiOpen = ref(false), fileInput = ref<HTMLInputElement | null>(null);
const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
const tabs = computed(() => [
  { id: 'all', label: '全部' }, { id: 'online', label: '在线' },
  { id: 'waiting', label: '等待接入', count: contacts.value.filter(c => c.status === 'WAITING_USER').length },
  { id: 'closed', label: '已完结' },
]);
const filtered = computed(() => contacts.value.filter(c => {
  const matches = filter.value === 'all' || (filter.value === 'online' && ['AI_ACTIVE', 'HUMAN_ACTIVE'].includes(c.status))
    || (filter.value === 'waiting' && c.status === 'WAITING_USER') || (filter.value === 'closed' && c.status === 'CLOSED');
  return matches && `${c.customer} ${c.id}`.toLowerCase().includes(search.value.trim().toLowerCase());
}).sort((a, b) => Date.parse(b.lastMessageAt) - Date.parse(a.lastMessageAt) || b.id - a.id));
const canSend = computed(() => isOwner.value && !!composer.value && composer.value.phase !== 'generating' && !composer.value.sending
  && (!!composer.value.text.trim() || !!composer.value.images.length));
const displayedOrders = computed(() => current.value ? (ordersExpanded.value ? current.value.orders : current.value.orders.slice(0, 1)) : []);
const selectedHistory = computed(() => current.value?.history.find(h => h.id === historyId.value) || current.value?.history[0]);
const assistLabel = computed(() => !composer.value?.enabled ? '已关闭，可直接手动回复'
  : composer.value.phase === 'generating' ? 'AI 正在生成回复内容'
  : composer.value.phase === 'error' ? '生成失败，可直接手动回复'
  : composer.value.phase === 'ready' ? '已生成，可编辑后发送' : '已开启，等待客户新消息');

watch([search, filter], () => {
  if (!filtered.value.some(c => c.id === selectedId.value)) select(filtered.value[0]?.id ?? null);
});
watch(selectedId, () => { ordersExpanded.value = false; emojiOpen.value = false; historyId.value = null; });
function chooseConversation(id: number) { select(id); mobileChat.value = true; }
function previewOf(row: WorkbenchConversation) {
  const message = [...(row.timelineHistory || []), ...row.messages].filter(m => m.kind !== 'divider').at(-1);
  return message?.kind === 'image' ? '[图片]' : message?.kind === 'order' ? '[订单卡片]' : message?.content || '等待开始沟通';
}
function openOrder(order: WorkbenchOrder) { selectedOrder.value = order; orderOpen.value = true; }
function openTicket(ticket: WorkbenchTicket) {
  if (!current.value) return;
  ticketConversation.value = current.value; ticketOrder.value = current.value.orders.find(o => o.id === ticket.orderId) || null;
  editingTicket.value = ticket; ticketOpen.value = true;
}
function newTicket() {
  if (!current.value?.orders.length) return;
  ticketConversation.value = current.value;
  if (current.value.orders.length > 1) chooseOrderOpen.value = true;
  else chooseTicketOrder(current.value.orders[0]);
}
function chooseTicketOrder(order: WorkbenchOrder) {
  chooseOrderOpen.value = false;
  if (!ticketConversation.value) return;
  ticketOrder.value = order;
  editingTicket.value = ticketConversation.value.tickets.find(t => t.orderId === order.id) || null;
  ticketOpen.value = true;
}
function ticketSaved(ticket: WorkbenchTicket) { ElMessage.success(editingTicket.value ? '工单已更新' : `工单 ${ticket.number} 已创建`); }
async function claimCurrent() { filter.value = 'all'; await claim(); }
async function reopenCurrent() { if (await reopen()) filter.value = 'all'; }
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !event.isComposing) { event.preventDefault(); void send(); }
}
function fileSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  Array.from(input.files || []).forEach(attach); input.value = '';
}
function addEmoji(emoji: string) { if (composer.value) { composer.value.text += emoji; composer.value.dirty = true; } emojiOpen.value = false; }
</script>

<template>
  <div class="wb-root" :class="{ 'wb-embedded': embedded }">
    <div class="wb-workspace">
      <main class="wb-columns" :class="{ 'show-mobile-chat': mobileChat, 'show-related': mobileRelated }">
        <section class="wb-conversations" aria-label="会话列表">
          <div class="wb-search"><Icon name="Search" /><input v-model="search" placeholder="搜索客户或会话" aria-label="搜索客户或会话" /><button v-if="search" class="wb-icon-button" @click="search = ''" aria-label="清空搜索"><Icon name="Close" /></button></div>
          <div class="wb-conversation-tabs" role="tablist" aria-label="会话状态"><button v-for="tab in tabs" :key="tab.id" :class="{ active: filter === tab.id }" role="tab" :aria-selected="filter === tab.id" @click="filter = tab.id">{{ tab.label }}<span v-if="tab.count" class="wb-count-amber">{{ tab.count }}</span></button></div>
          <div v-if="loadError" class="live-error" role="alert">{{loadError}} <button @click="refresh">重试</button></div><div class="wb-conversation-rows">
            <div v-if="loading" class="wb-list-loading" aria-label="正在加载会话"><div v-for="i in 5" :key="i" class="wb-skeleton-row"></div></div>
            <button v-for="row in filtered" v-else :key="row.id" class="wb-conversation-row" :class="{ selected: selectedId === row.id, unread: row.unread }" :aria-label="`${row.customer}，${statusLabels[row.status]}，会话 ${row.id}`" :aria-pressed="selectedId === row.id" @click="chooseConversation(row.id)">
              <span class="wb-unread-dot" :class="{ waiting: row.status === 'WAITING_USER' }"></span><span class="wb-avatar" :class="row.tone">{{ row.avatar }}</span><span class="wb-conversation-summary"><span class="wb-conversation-first"><strong>{{ row.customer }}</strong><time>{{ timeOf(row.lastMessageAt) }}</time></span><span class="wb-conversation-status"><span class="wb-status" :class="row.status === 'WAITING_USER' ? 'waiting' : row.status === 'HUMAN_ACTIVE' ? 'human' : row.status === 'AI_ACTIVE' ? 'ai' : 'closed'">{{ row.status === 'HUMAN_ACTIVE' && row.agentId !== staff.id ? `${row.agent?.replace('客服', '')}接待` : statusLabels[row.status] }}</span></span><span class="wb-conversation-preview">{{ previewOf(row) }}</span></span>
            </button>
            <div v-if="!loading && !filtered.length" class="wb-list-empty"><Icon name="Search" /><strong>没有匹配的会话</strong><span>试试其他名称或会话编号</span><button v-if="search" class="wb-text-button" @click="search = ''">清空搜索</button></div>
          </div>
          <div class="wb-list-footer"><span class="wb-dot" :class="{ offline: !staff.online }"></span>{{ staff.online ? '您已在线，可接入等待中的会话' : '您已离线，已有会话仍可继续处理' }}</div>
        </section>

        <section class="wb-chat" aria-label="聊天区">
          <template v-if="current">
            <div class="wb-chat-head"><button class="wb-icon-button wb-mobile-back" @click="mobileChat = false" aria-label="返回会话列表"><Icon name="ArrowLeft" /></button><span class="wb-avatar" :class="current.tone">{{ current.avatar }}</span><div class="wb-chat-identity"><div><h2>{{ current.customer }}</h2><span class="wb-status" :class="current.status === 'WAITING_USER' ? 'waiting' : current.status === 'HUMAN_ACTIVE' ? 'human' : current.status === 'CLOSED' ? 'closed' : 'ai'">{{ statusLabels[current.status] }}</span></div><small>{{ current.status === 'HUMAN_ACTIVE' ? `当前客服：${current.agent?.replace('客服', '')}` : current.status === 'WAITING_USER' ? '本店在线客服共享等待' : current.status === 'AI_ACTIVE' ? 'AI 正在为客户接待' : `会话 #${current.id}` }}</small></div><div class="wb-chat-actions"><button v-if="current.history.length" class="wb-text-button wb-history-link" @click="historyOpen = true">历史会话</button><button class="wb-icon-button wb-mobile-related" @click="mobileRelated = !mobileRelated" aria-label="查看相关订单与工单"><Icon name="ShoppingBag" /></button><button v-if="isOwner" class="wb-btn wb-close-button" :disabled="actionBusy || composer?.sending" @click="requestClose">完结会话</button><button v-else-if="current.status === 'WAITING_USER' || (!capabilities.assist && current.status === 'AI_ACTIVE')" class="wb-btn primary" :disabled="actionBusy || !staff.online" @click="claimCurrent"><Icon v-if="actionBusy" name="Loading" spin />接入会话</button></div></div>

            <MessageTimeline :key="current.id" :messages="timeline" :orders="current.orders" :customer="current.customer" :tone="current.tone" :active="mobileChat" @order="openOrder" @image="imageUrl = $event; imageOpen = true" />

            <div v-if="isOwner && composer" class="wb-composer" :class="{ generating: composer.phase === 'generating' }">
              <div v-if="capabilities.assist" class="wb-assist-bar"><div class="wb-assist-state"><Icon :name="composer.phase === 'generating' ? 'Loading' : 'MagicStick'" :spin="composer.phase === 'generating'" /><strong>AI 回复辅助</strong><span :class="{ 'has-error': composer.phase === 'error' }" role="status">{{ assistLabel }}</span></div><button class="wb-switch" :class="{ on: composer.enabled }" role="switch" :aria-checked="composer.enabled" :aria-label="composer.enabled ? '关闭 AI 回复辅助' : '开启 AI 回复辅助'" :disabled="composer.sending" @click="toggleAssist"><span></span></button></div>
              <div class="wb-input-box"><textarea :value="composer.text" @input="composer.text = ($event.target as HTMLTextAreaElement).value; composer.dirty = true" @keydown="onKeydown" :readonly="composer.phase === 'generating' || composer.sending" :placeholder="composer.phase === 'generating' ? 'AI 正在生成回复内容，您可以随时关闭辅助…' : '输入回复内容…'" aria-label="回复内容" rows="3" maxlength="3000" />
                <div v-if="composer.images.length" class="wb-attachments"><div v-for="(image, index) in composer.images" :key="image.url"><img :src="image.url" :alt="image.name" /><button :disabled="composer.sending" @click="composer.images.splice(index, 1)" aria-label="移除待发送图片"><Icon name="Close" /></button></div></div>
                <div class="wb-composer-bottom"><div class="wb-composer-tools"><div class="wb-emoji-wrap"><button class="wb-icon-button wb-emoji-button" :disabled="composer.phase === 'generating' || composer.sending" @click="emojiOpen = !emojiOpen" aria-label="插入表情"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6" /><circle cx="9" cy="10" r="1" fill="currentColor" /><circle cx="15" cy="10" r="1" fill="currentColor" /><path d="M8 14c1.2 3 6.8 3 8 0" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg></button><div v-if="emojiOpen" class="wb-emoji-picker" role="group" aria-label="选择表情"><button v-for="emoji in ['😊', '👌', '🙏', '🌷', '👍', '🤝']" :key="emoji" @click="addEmoji(emoji)">{{ emoji }}</button></div></div><button v-if="capabilities.attachments" class="wb-icon-button" :disabled="composer.phase === 'generating' || composer.sending" @click="fileInput?.click()" aria-label="添加图片"><Icon name="Picture" /></button><input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden @change="fileSelected" /><span class="wb-sender-label">以{{staff.name}}的身份回复</span></div><div class="wb-send-actions"><small>{{ isMac ? '⌘' : 'Ctrl' }} Enter 发送</small><button class="wb-btn primary wb-send-button" :disabled="!canSend" @click="send"><Icon v-if="composer.sending" name="Loading" spin />{{ composer.sending ? '发送中' : '发送' }}</button></div></div>
              </div><p v-if="composer.phase === 'error'" class="wb-assist-error" role="alert">{{ composer.error }}</p>
            </div>
            <div v-else class="wb-reception-state" :class="{ waiting: current.status === 'WAITING_USER' }"><Icon :name="current.status === 'CLOSED' ? 'CircleCheck' : current.status === 'WAITING_USER' ? 'Clock' : 'ChatDotRound'" /><div><strong>{{ current.status === 'CLOSED' ? '本次会话已完结' : current.status === 'WAITING_USER' ? '客户正在等待人工接入' : current.status === 'AI_ACTIVE' ? 'AI 正在接待中' : `当前由${current.agent}接待` }}</strong><p>{{ current.status === 'CLOSED' ? capabilities.tickets ? '工单记录继续保留，您可以重新发起会话。' : '聊天记录已保留，您可以重新发起会话。' : current.status === 'WAITING_USER' ? staff.online ? capabilities.assist ? '接入后即可回复，AI 将为您提供回复建议。' : '接入后即可回复客户。' : '切换为在线后即可接入，已有会话不受影响。' : current.status === 'AI_ACTIVE' ? '需要人工处理时，会话会进入等待接入。' : '您可以查看消息和关联资料，当前不能代为回复。' }}</p></div><button v-if="current.status === 'CLOSED'" class="wb-btn" :disabled="!staff.online || actionBusy" @click="reopenCurrent">重新发起会话</button></div>
          </template>
          <div v-else class="wb-chat-empty"><span><Icon name="ChatLineRound" /></span><h2>{{ loading ? '正在准备工作台' : '选择一段会话，开始接待' }}</h2><p>{{ loading ? '正在加载会话与关联资料' : '客户消息、订单和工单会显示在这里' }}</p></div>
        </section>

        <button v-if="mobileRelated" class="wb-related-backdrop" @click="mobileRelated = false" aria-label="关闭关联资料"></button>
        <aside class="wb-related" aria-label="相关订单与客服工单">
          <div class="wb-related-mobile-head"><strong>关联资料</strong><button class="wb-icon-button" @click="mobileRelated = false" aria-label="关闭关联资料"><Icon name="Close" /></button></div>
          <section class="wb-related-section"><div class="wb-related-title"><h2>相关订单 <span class="wb-count-neutral">{{ current?.orders.length || 0 }}</span></h2></div>
            <div v-for="order in displayedOrders" :key="order.id" class="wb-order-card"><div class="wb-order-card-head"><strong>{{ order.number }}</strong><span class="wb-order-status" :class="{ delivered: order.status === '已签收' }">{{ order.status }}</span></div><div class="wb-order-product"><ProductThumbnail :kind="order.thumbnail" :src="order.imageUrl" /><div><strong>{{ order.product }}</strong><small>{{ order.variant }} × {{ order.quantity }}</small><b>{{ money(order.amount) }}</b></div></div><button class="wb-order-detail-link" @click="openOrder(order)">订单详情<Icon name="ArrowRight" /></button></div>
            <button v-if="current && current.orders.length > 1" class="wb-expand-orders" @click="ordersExpanded = !ordersExpanded">{{ ordersExpanded ? '收起其他订单' : `查看另外 ${current.orders.length - 1} 笔订单` }}<Icon :name="ordersExpanded ? 'ArrowDown' : 'ArrowRight'" /></button>
            <div v-if="!current?.orders.length" class="wb-related-empty"><Icon name="ShoppingBag" /><p>{{ current ? '暂无关联订单' : '选择会话后查看订单' }}</p><small v-if="current">核实订单后，再记录售后诉求</small></div>
          </section>
          <section class="wb-related-section wb-ticket-section"><div class="wb-related-title"><h2>客服工单 <span v-if="current?.tickets.length" class="wb-count-neutral">{{ current.tickets.length }}</span></h2><button v-if="capabilities.tickets" class="wb-text-button" :disabled="!current?.orders.length" @click="newTicket"><Icon name="Plus" />新增</button></div>
            <article v-for="ticket in current?.tickets || []" :key="ticket.id" class="wb-ticket-card"><div class="wb-ticket-card-head"><strong>{{ ticket.number }}</strong><span class="wb-status" :class="ticket.completion === 'DONE' ? 'closed' : 'waiting'">{{ ticket.completion === 'DONE' ? '已完成' : '待完成' }}</span></div><div class="wb-ticket-tags"><span v-for="type in ticket.types" :key="type">{{ ticketTypeLabels[type] }}</span></div><p>{{ ticket.description }}</p><div class="wb-ticket-card-foot"><small>{{ ticket.source === 'AI' ? 'AI 创建' : '客服创建' }} · {{ timeOf(ticket.createdAt) }}</small><button class="wb-text-button" @click="openTicket(ticket)">查看详情<Icon name="ArrowRight" /></button></div></article>
            <div v-if="!current?.tickets.length" class="wb-related-empty wb-empty-tickets"><Icon name="Document" /><p>暂无客服工单</p><small>{{ !capabilities.tickets ? '工单功能暂未开放' : current?.orders.length ? '需要跟进的售后诉求可以记录在这里' : '关联订单后即可新增工单' }}</small></div>
          </section>
        </aside>
      </main>
    </div>

    <OrderDetailDialog v-model="orderOpen" :order="selectedOrder" />
    <TicketDialog v-model="ticketOpen" :conversation="ticketConversation" :order="ticketOrder" :ticket="editingTicket" :save="saveTicket" @saved="ticketSaved" />
    <el-dialog v-model="closeConfirm" title="完结本次会话？" width="420px" class="wb-dialog" align-center append-to-body :close-on-click-modal="!actionBusy" :close-on-press-escape="!actionBusy" :show-close="!actionBusy">
      <p class="pv-close-description">确认完结与{{ closingConversation?.customer }}的本次会话吗？{{ capabilities.assist ? '聊天记录和客服工单会保留，客户再次发消息时将由 AI 优先接待。' : '聊天记录会保留，客户再次发消息时将开始新的接待，等待客服接入。' }}</p>
      <template #footer><button class="wb-btn" :disabled="actionBusy" @click="closeConfirm=false">继续接待</button><button class="wb-btn primary" :disabled="actionBusy" @click="confirmClose">{{ actionBusy ? '正在完结' : '确认完结' }}</button></template>
    </el-dialog>
    <el-dialog v-model="chooseOrderOpen" title="选择本次工单关联的订单" width="520px" class="wb-dialog" align-center><p class="wb-dialog-intro">一张工单对应一笔订单，选择后关联信息将固定。</p><button v-for="order in ticketConversation?.orders || []" :key="order.id" class="wb-order-choice" @click="chooseTicketOrder(order)"><ProductThumbnail :kind="order.thumbnail" :src="order.imageUrl" small /><span><strong>{{ order.product }}</strong><small>{{ order.number }}</small><small>{{ order.variant }} × {{ order.quantity }}</small></span><span class="wb-choice-action">{{ ticketConversation?.tickets.some(t => t.orderId === order.id) ? '补充诉求' : '新增记录' }}<Icon name="ArrowRight" /></span></button></el-dialog>
    <el-drawer v-model="historyOpen" :title="`${current?.customer || ''}的历史会话`" size="min(760px, 100vw)" class="wb-history-drawer"><template v-if="current"><p class="wb-dialog-intro">查看本店该客户以往的接待记录</p><div class="wb-history-layout"><div class="wb-history-list"><button v-for="history in current.history" :key="history.id" :class="{ selected: selectedHistory?.id === history.id }" @click="historyId = history.id"><strong>{{ dateOf(history.endedAt) }}</strong><span>{{ history.agent }} · 已完结</span><p>{{ history.summary }}</p></button></div><div v-if="selectedHistory" class="wb-history-messages"><div class="wb-history-meta">会话 #{{ selectedHistory.id }} · {{ selectedHistory.agent }}</div><MessageTimeline :key="selectedHistory.id" :messages="selectedHistory.messages" :orders="current.orders" :customer="current.customer" :tone="current.tone" history @order="openOrder" @image="imageUrl = $event; imageOpen = true" /></div></div></template></el-drawer>
    <el-dialog v-model="imageOpen" title="会话图片" width="min(760px, 92vw)" class="wb-dialog wb-image-dialog" align-center><img :src="imageUrl" alt="会话图片大图" /></el-dialog>
  </div>
</template>
