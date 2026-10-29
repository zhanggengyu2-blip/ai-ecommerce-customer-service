import { computed, onMounted, onUnmounted, reactive, ref, type InjectionKey } from 'vue';
import { ElMessage } from 'element-plus/es/components/message/index.mjs';
import { createMockWorkbenchRepository, type WorkbenchRepository } from './mockRepository';
import type { TicketInput, WorkbenchConversation, WorkbenchOrder, WorkbenchTicket } from './types';

export interface ComposerState {
  text: string;
  enabled: boolean;
  phase: 'idle' | 'generating' | 'ready' | 'error';
  error: string;
  generation: number;
  dirty: boolean;
  sending: boolean;
  images: { url: string; name: string }[];
}

export function useWorkbench(options: { repository?: WorkbenchRepository; live?: boolean; pollMs?: number } = {}) {
  const repository = options.repository || createMockWorkbenchRepository();
  const capabilities = { assist: !options.live, attachments: !options.live, tickets: !options.live };
  const loadError = ref('');
  let refreshVersion = 0, refreshing = false, disposed = false;
  let poll: ReturnType<typeof setInterval> | undefined;
  const conversations = ref<WorkbenchConversation[]>([]);
  const staff = reactive({ id: 1, name: '客服小林', online: true, avatar: '' });
  const selectedId = ref<number | null>(options.live ? null : 101);
  const loading = ref(true);
  const presenceBusy = ref(false);
  const actionBusy = ref(false);
  const drafts = reactive<Record<number, ComposerState>>({});
  const controllers = new Map<number, AbortController>();
  const objectUrls = new Set<string>();
  const current = computed(() => conversations.value.find(c => c.id === selectedId.value) || null);
  const isOwner = computed(() => !!current.value && current.value.status === 'HUMAN_ACTIVE' && current.value.agentId === staff.id);
  function draftFor(id: number): ComposerState {
    return drafts[id] ||= { text: '', enabled: capabilities.assist, phase: 'idle', error: '', generation: 0, dirty: false, sending: false, images: [] };
  }
  const composer = computed(() => current.value ? draftFor(current.value.id) : null);
  function update(row: WorkbenchConversation) {
    refreshVersion++;
    if (options.live) conversations.value = conversations.value.filter(c => c.customerId !== row.customerId || c.id === row.id);
    const index = conversations.value.findIndex(c => c.id === row.id);
    if (index >= 0) conversations.value[index] = row;
    else conversations.value.push(row);
  }
  function select(id: number | null) {
    selectedId.value = id;
    const row = conversations.value.find(c => c.id === id);
    if (row) { row.unread = false; repository.markRead(row.id); }
  }
  function cancel(id: number) {
    controllers.get(id)?.abort(); controllers.delete(id);
    const draft = draftFor(id); draft.generation++; draft.phase = 'idle'; draft.error = '';
  }
  async function generate(id: number, fail = false) {
    if (!capabilities.assist) return;
    const row = conversations.value.find(c => c.id === id);
    if (!row || row.status !== 'HUMAN_ACTIVE' || row.agentId !== staff.id) return;
    cancel(id);
    const draft = draftFor(id); if (!draft.enabled) return;
    const generation = draft.generation;
    const controller = new AbortController(); controllers.set(id, controller);
    draft.phase = 'generating';
    try {
      const content = await repository.generate(id, controller.signal, fail);
      const fresh = conversations.value.find(c => c.id === id);
      if (draft.generation !== generation || !draft.enabled || fresh?.status !== 'HUMAN_ACTIVE' || fresh.agentId !== staff.id) return;
      draft.text = content; draft.phase = 'ready'; draft.dirty = false;
    } catch (error) {
      if (controller.signal.aborted || draft.generation !== generation) return;
      draft.phase = 'error'; draft.error = error instanceof Error ? error.message : '生成失败，请直接手动回复。';
    } finally {
      if (controllers.get(id) === controller) controllers.delete(id);
    }
  }
  function toggleAssist() {
    if (!current.value || !isOwner.value) return;
    const draft = draftFor(current.value.id); draft.enabled = !draft.enabled;
    if (!draft.enabled) cancel(current.value.id);
    else void generate(current.value.id);
  }
  async function setOnline(online: boolean) {
    if (presenceBusy.value) return;
    presenceBusy.value = true;
    try { await repository.setOnline(online); staff.online = online;
      ElMessage.success(online ? '已上线，可以接入新会话' : '已离线，仍可继续处理已有会话');
    } catch (error) { ElMessage.warning((error as Error).message);
    } finally { presenceBusy.value = false; }
  }
  async function claim() {
    if (!current.value || actionBusy.value) return;
    const id = current.value.id; actionBusy.value = true;
    try { update(await repository.claim(id)); ElMessage.success('已接入会话'); void generate(id); }
    catch (error) { ElMessage.warning((error as Error).message); void refresh(); }
    finally { actionBusy.value = false; }
  }
  async function close(id = current.value?.id) {
    if (id === undefined || actionBusy.value) return;
    const row = conversations.value.find(c => c.id === id);
    if (row?.status !== 'HUMAN_ACTIVE' || row.agentId !== staff.id || draftFor(id).sending) return;
    actionBusy.value = true;
    try { update(await repository.close(id)); cancel(id); ElMessage.success(options.live ? '本次会话已完结，聊天记录已保留' : '本次会话已完结，工单记录继续保留'); }
    catch (error) { ElMessage.warning((error as Error).message); }
    finally { actionBusy.value = false; }
  }
  async function reopen() {
    if (!current.value || actionBusy.value) return false;
    actionBusy.value = true;
    try {
      const row = await repository.reopen(current.value.id); update(row); select(row.id);
      const draft = draftFor(row.id); draft.enabled = capabilities.assist; void generate(row.id); return true;
    } catch (error) { ElMessage.warning((error as Error).message); return false; }
    finally { actionBusy.value = false; }
  }
  async function send() {
    if (!current.value || !isOwner.value) return;
    const id = current.value.id, draft = draftFor(id);
    if (draft.sending || draft.phase === 'generating' || (!draft.text.trim() && !draft.images.length)) return;
    draft.sending = true;
    try {
      update(await repository.send(id, draft.text, draft.images.map(i => i.url)));
      draft.text = ''; draft.images = []; draft.phase = 'idle'; draft.dirty = false; draft.error = '';
    } catch (error) { ElMessage.warning((error as Error).message); }
    finally { draft.sending = false; }
  }
  function attach(file: File) {
    if (!capabilities.attachments) return;
    if (!current.value || !isOwner.value) return;
    const draft = draftFor(current.value.id);
    if (draft.phase === 'generating' || draft.sending) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
      ElMessage.warning('请选择不超过 5 MB 的 JPG、PNG 或 WebP 图片'); return;
    }
    if (draft.images.length >= 3) { ElMessage.warning('一次最多发送 3 张图片'); return; }
    const url = URL.createObjectURL(file); objectUrls.add(url); draft.images.push({ url, name: file.name });
  }
  async function incoming(text: string) {
    if (!current.value) return;
    const id = current.value.id;
    update(await repository.addCustomerMessage(id, text));
    const draft = draftFor(id);
    if (draft.enabled && !draft.text && draft.phase !== 'generating') void generate(id);
  }
  async function saveTicket(input: TicketInput, existing?: WorkbenchTicket) {
    const result = await repository.saveTicket(input, existing && { id: existing.id, revision: existing.revision });
    const row = conversations.value.find(c => c.id === input.conversationId);
    if (row) { const index = row.tickets.findIndex(t => t.id === result.id);
      if (index >= 0) row.tickets[index] = result; else row.tickets.push(result); }
    return result;
  }
  async function completeTicket(id: number) {
    const ticket = await repository.completeTicket(id);
    const row = conversations.value.find(c => c.id === ticket.conversationId);
    if (row) { const index = row.tickets.findIndex(t => t.id === id); if (index >= 0) row.tickets[index] = ticket; }
    return ticket;
  }
  function updateOrder(id: number, patch: Partial<WorkbenchOrder>) {
    const plain = JSON.parse(JSON.stringify(patch)); repository.updateOrder(id, plain);
    conversations.value.forEach(c => c.orders.forEach(o => { if (o.id === id) Object.assign(o, plain); }));
  }
  async function refresh() {
    if (refreshing || disposed) return;
    refreshing = true;
    const version = ++refreshVersion;
    try {
      const snapshot = await repository.load();
      if (disposed || version !== refreshVersion) return;
      const customerId = current.value?.customerId;
      conversations.value = snapshot.conversations; Object.assign(staff, snapshot.staff);
      if (!conversations.value.some(c => c.id === selectedId.value)) {
        select(conversations.value.find(c => c.customerId === customerId)?.id ?? conversations.value[0]?.id ?? null);
      }
      loadError.value = '';
    } catch (error) { if (!disposed) loadError.value = (error as Error).message; }
    finally { refreshing = false; loading.value = false; }
  }
  onMounted(async () => {
    try {
      await refresh();
      const first = conversations.value.find(c => c.id === 101);
      if (first && !options.live) Object.assign(draftFor(first.id), { text: first.suggestion, phase: 'ready' });
      if (options.pollMs) poll = setInterval(() => {
        if (!actionBusy.value && !presenceBusy.value && !Object.values(drafts).some(d => d.sending)) void refresh();
      }, options.pollMs);
    } finally { loading.value = false; }
  });
  onUnmounted(() => { disposed = true; clearInterval(poll); controllers.forEach(c => c.abort()); objectUrls.forEach(url => URL.revokeObjectURL(url)); });
  return { conversations, current, selectedId, staff, loading, presenceBusy, actionBusy, composer, isOwner,
    capabilities, loadError, refresh, select, toggleAssist, setOnline, claim, close, reopen, send, attach, incoming, saveTicket, generate, completeTicket, updateOrder };
}
export type WorkbenchContext = ReturnType<typeof useWorkbench>;
export const WorkbenchKey: InjectionKey<WorkbenchContext> = Symbol('workbench');
