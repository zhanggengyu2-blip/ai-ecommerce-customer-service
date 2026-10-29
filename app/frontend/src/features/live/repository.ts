import type { WorkbenchRepository } from '../workbench/mockRepository';
import type { WorkbenchConversation, WorkbenchMessage } from '../workbench/types';
import { allPages, readMessages, staffApi as api, type Reception, type Staff, type StoredMessage } from './api';

export function messageView(m: StoredMessage): WorkbenchMessage {
  return { id: m.id, sender: m.sender_type === 'CUSTOMER' ? 'customer' : m.sender_type === 'AGENT' ? 'agent' : m.sender_type === 'AI' ? 'ai' : 'system',
    name: m.sender_name, kind: 'text', content: m.content, createdAt: m.created_at,
    citations: m.citations, traceId: m.trace_id || undefined };
}
export function createLiveRepository(): WorkbenchRepository {
  const receptions = new Map<number, Reception>();
  const threadMessages = new Map<number, StoredMessage[]>();
  const rows = new Map<number, WorkbenchConversation>();
  const revisions = new Map<number, number>();
  const pending = new Map<string, { key: string; content: string }>();
  const unavailable = async (): Promise<never> => { throw new Error('此功能暂未开放。'); };

  async function convert(c: Reception): Promise<WorkbenchConversation> {
    receptions.set(c.id, c);
    const messages = await readMessages(api, `/api/agent/threads/${c.thread_id}/messages`, threadMessages.get(c.thread_id));
    threadMessages.set(c.thread_id, messages);
    const history = await allPages<Reception>(api, `/api/admin/conversations?customer_id=${c.user_id}`);
    history.forEach(h => receptions.set(h.id, h));
    const row: WorkbenchConversation = { id: c.id, customerId: c.user_id, customer: c.customer_name,
      avatar: c.customer_name[0] || '客', tone: 'blue', status: c.status,
      agentId: c.current_agent_id, agent: c.agent_name, lastMessageAt: c.last_message_at,
      waitingSince: c.handoff_requested_at || undefined, unread: false,
      messages: messages.filter(m => m.conversation_id === c.id).map(messageView),
      timelineHistory: [...messages.filter(m => m.conversation_id !== c.id).map(messageView),
        ...(messages.some(m => m.conversation_id !== c.id) ? [{ id: -c.id, sender: 'system' as const,
          name: '', kind: 'divider' as const, content: `本次接待 #${c.id}`, createdAt: c.started_at }] : [])],
      orders: [], tickets: [], suggestion: '', summary: c.consultation_summary || undefined,
      history: history.filter(h => h.id !== c.id).map(h => ({ id: h.id, endedAt: h.closed_at || h.last_message_at,
        agent: h.agent_name || '尚未接入人工', summary: h.consultation_summary || '尚未生成摘要',
        messages: messages.filter(m => m.conversation_id === h.id).map(messageView) })) };
    rows.set(c.id, row); return row;
  }
  async function transition(id: number, action: string) {
    const c = receptions.get(id);
    if (!c) throw new Error('接待状态已变化，请刷新后重试。');
    const slot = `${action}:${id}`;
    const value = pending.get(slot) || { key: crypto.randomUUID(), content: String(c.reception_epoch) };
    if (action === 'reopen') pending.set(slot, value);
    const result = await api<Reception>(`/api/agent/conversations/${id}/${action}`, {
      expected_epoch: action === 'reopen' ? Number(value.content) : c.reception_epoch,
      ...(action === 'reopen' ? { request_id: value.key } : {}),
    });
    pending.delete(slot); revisions.delete(result.thread_id);
    return convert(result);
  }
  return {
    async load() {
      const [staff, items] = await Promise.all([api<Staff>('/api/auth/me'), allPages<Reception>(api, '/api/agent/threads')]);
      const conversations: WorkbenchConversation[] = [];
      for (const c of [...new Map(items.map(c => [c.thread_id, c])).values()]) {
        const cached = rows.get(c.id);
        conversations.push(cached && revisions.get(c.thread_id) === c.thread_revision ? cached : await convert(c));
        revisions.set(c.thread_id, c.thread_revision || 0);
      }
      return { staff: { id: staff.id, name: staff.display_name, online: staff.work_status === 'ONLINE' }, conversations };
    },
    async setOnline(online) { await api('/api/agent/presence', { status: online ? 'ONLINE' : 'OFFLINE' }, 'PUT'); },
    markRead() {},
    claim: id => transition(id, 'claim'), close: id => transition(id, 'close'), reopen: id => transition(id, 'reopen'),
    async send(id, text, images) {
      if (images.length) return unavailable();
      const content = text.trim(), slot = `send:${id}`;
      let value = pending.get(slot);
      if (!value || value.content !== content) { value = { key: crypto.randomUUID(), content }; pending.set(slot, value); }
      await api(`/api/agent/conversations/${id}/messages`, { client_message_id: value.key, content });
      const c = await api<Reception>(`/api/admin/conversations/${id}`);
      revisions.delete(c.thread_id);
      const row = await convert(c); pending.delete(slot); return row;
    },
    addCustomerMessage: unavailable, generate: unavailable, saveTicket: unavailable, completeTicket: unavailable,
    updateOrder() { throw new Error('此功能暂未开放。'); },
  };
}
