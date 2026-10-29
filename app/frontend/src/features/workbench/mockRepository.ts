import type {
  WorkbenchSnapshot, WorkbenchConversation, WorkbenchMessage, WorkbenchOrder, WorkbenchTicket, TicketInput,
} from './types';
import { ticketTypeLabels } from './types';

export class WorkbenchError extends Error {
  constructor(public code: string, message: string, public ticketId?: number) { super(message); }
}

// The page depends on this contract, not on the fixture data or timers below.
export interface WorkbenchRepository {
  load(): Promise<WorkbenchSnapshot>;
  setOnline(online: boolean): Promise<void>;
  markRead(id: number): void;
  claim(id: number): Promise<WorkbenchConversation>;
  close(id: number): Promise<WorkbenchConversation>;
  reopen(id: number): Promise<WorkbenchConversation>;
  send(id: number, text: string, images: string[]): Promise<WorkbenchConversation>;
  addCustomerMessage(id: number, text: string): Promise<WorkbenchConversation>;
  generate(id: number, signal: AbortSignal, fail?: boolean): Promise<string>;
  saveTicket(input: TicketInput, existing?: { id: number; revision: number }): Promise<WorkbenchTicket>;
  completeTicket(id: number): Promise<WorkbenchTicket>;
  updateOrder(id: number, patch: Partial<WorkbenchOrder>): void;
}

const clone = <T>(value: T): T => structuredClone(value);
const delay = (ms = 160) => new Promise<void>(resolve => setTimeout(resolve, ms));

function createFixtures(): WorkbenchSnapshot {
  const now = Date.now();
  const ago = (minutes: number) => new Date(now - minutes * 60_000).toISOString();
  let messageId = 100;
  const message = (sender: WorkbenchMessage['sender'], name: string, content: string, minutes: number,
    kind: WorkbenchMessage['kind'] = 'text', orderId?: number): WorkbenchMessage => ({
    id: messageId++, sender, name, content, createdAt: ago(minutes), kind, orderId,
  });
  const trousers: WorkbenchOrder = {
    id: 201, number: 'TB202610190028', product: '休闲直筒长裤', variant: '黑色 / M 码', quantity: 2,
    amount: 258, thumbnail: 'trousers', status: '已签收', paidAt: ago(60 * 24 * 3),
    receiver: '林女士 · 138****6028', address: '上海市徐汇区 · 收货地址已核验',
    carrier: '顺丰速运', tracking: 'SF158****6028',
  };
  const knit: WorkbenchOrder = {
    ...trousers, id: 202, number: 'TB202610180157', product: '柔软圆领针织衫', variant: '燕麦色 / 均码',
    quantity: 1, amount: 189, thumbnail: 'knit', status: '运输中', carrier: '中通快递', tracking: 'ZT756****0157',
  };
  const addressOrder: WorkbenchOrder = {
    ...trousers, id: 203, number: 'TB202610190036', product: '基础款牛津纺衬衫', variant: '浅蓝色 / L 码',
    quantity: 1, amount: 159, thumbnail: 'shirt', status: '待发货', receiver: '陈先生 · 139****1036',
    address: '浙江省杭州市 · 收货地址已核验', carrier: '尚未发货', tracking: '—',
  };
  const history = [{
    id: 85, endedAt: ago(60 * 24 * 4), agent: '客服小周', summary: '咨询长裤尺码，已提供商品尺寸参考。',
    messages: [
      message('customer', '林女士', '身高 165，平时穿 M 码，这款裤子怎么选？', 60 * 24 * 4 + 4),
      message('agent', '客服小周', '您好，可以参考商品详情中的尺码表。您也可以提供平时合适的裤长和腰围，我帮您核对。', 60 * 24 * 4 + 3),
      message('customer', '林女士', '好的，我先对一下，谢谢。', 60 * 24 * 4 + 1),
    ],
  }];
  const lin: WorkbenchConversation = {
    id: 101, customerId: 1001, customer: '林女士', avatar: '林', tone: 'blue', status: 'HUMAN_ACTIVE',
    agentId: 1, agent: '客服小林', lastMessageAt: ago(0), unread: false, orders: [trousers, knit],
    messages: [
      message('customer', '林女士', '这条裤子想退一件，另一件换成 L 码，可以吗？', 8),
      message('ai', 'AI 客服', '我先帮您核实，请确认对应的订单。', 7.7),
      message('customer', '林女士', '', 7, 'order', 201),
      message('ai', 'AI 客服', '已找到这笔订单，我为您联系人工客服继续处理。', 6.5),
      message('system', '', '以上为 AI 自动回复 · 客服小林已接入', 6, 'divider'),
      message('agent', '客服小林', '您好，我是小林。我先帮您核对这两件商品。', 5),
      message('customer', '林女士', '一件退货退款，另一件换成 L 码。', 0),
    ],
    tickets: [{
      id: 301, number: 'CS202610190016', conversationId: 101, customerId: 1001, orderId: 201,
      types: ['RETURN_REFUND', 'EXCHANGE'], description: '本单 2 件：1 件退货退款，1 件换成 L 码。',
      refundAmount: '', exchangeTarget: 'L 码', newAddress: '', completion: 'PENDING', source: 'AI',
      createdAt: ago(0), revision: 1,
    }],
    suggestion: '收到，我先核对商品和售后条件，再分别为您说明退货和换码的办理方式。', history,
  };
  const base = (id: number, customer: string, avatar: string): WorkbenchConversation => ({
    id, customerId: id + 900, customer, avatar, tone: 'slate', status: 'AI_ACTIVE', agentId: null, agent: null,
    lastMessageAt: ago(id - 100), unread: false, messages: [], orders: [], tickets: [], suggestion: '', history: [],
  });
  const chen: WorkbenchConversation = {
    ...base(102, '陈先生', '陈'), tone: 'slate', status: 'WAITING_USER', unread: true, waitingSince: ago(3),
    orders: [addressOrder], lastMessageAt: ago(2),
    messages: [
      message('customer', '陈先生', '这笔订单可以修改地址吗？还没有发货。', 3),
      message('customer', '陈先生', '', 2.8, 'order', 203),
      message('ai', 'AI 客服', '这笔订单目前待发货，我正在为您联系人工客服核实修改方式。', 2),
    ], suggestion: '您好，我是小林。请提供需要修改的收件人、联系电话和完整地址，我先为您核实。',
  };
  const wang: WorkbenchConversation = {
    ...base(103, '王女士', '王'), tone: 'rose', status: 'WAITING_USER', unread: true, waitingSince: ago(7),
    lastMessageAt: ago(4), orders: [{ ...trousers, id: 204, number: 'TB202610170092', receiver: '王女士 · 136****0092' }],
    messages: [
      message('customer', '王女士', '裤子有一处开线了，怎么处理呢？', 7),
      message('ai', 'AI 客服', '您可以先说明开线位置，我为您联系人工客服进一步核实。', 6.8),
      message('ai', 'AI 客服', '抱歉让您久等了，客服正在处理其他咨询。您的问题已保留，我们会尽快为您接续处理。', 4),
    ], suggestion: '您好，让您久等了。我来帮您核实开线的情况，方便提供一张问题位置的照片吗？',
  };
  const zhao: WorkbenchConversation = {
    ...base(104, '赵先生', '赵'), tone: 'teal', lastMessageAt: ago(7), unread: true,
    orders: [{ ...knit, id: 205, number: 'TB202610180112', receiver: '赵先生 · 137****0112' }],
    messages: [
      message('customer', '赵先生', '针织衫现在到哪里了？', 8),
      message('ai', 'AI 客服', '这笔订单正在运输中，您可以打开订单详情查看承运方和物流单号。', 7),
    ],
  };
  const zhou: WorkbenchConversation = {
    ...base(105, '周女士', '周'), tone: 'amber', lastMessageAt: ago(10),
    messages: [message('customer', '周女士', '请问尺码推荐有吗？', 11),
      message('ai', 'AI 客服', '方便告诉我您想了解哪款商品，以及平时穿着的尺码吗？我先帮您核对。', 10)],
  };
  const xu: WorkbenchConversation = {
    ...base(106, '许先生', '许'), summary: '客户查询包裹进度，已确认签收。', status: 'CLOSED', lastMessageAt: ago(13), agentId: 1, agent: '客服小林',
    orders: [{ ...addressOrder, id: 206, number: 'TB202610160019', status: '已签收', receiver: '许先生 · 138****0019' }],
    messages: [message('customer', '许先生', '查一下我的快递。', 18),
      message('ai', 'AI 客服', '已为您找到订单，物流信息显示包裹已签收，请确认是否收到。', 17),
      message('customer', '许先生', '谢谢，已经收到了！', 13),
      message('system', '', '本次会话已完结', 12, 'divider')],
  };
  const zhang: WorkbenchConversation = {
    ...base(107, '张女士', '张'), tone: 'rose', status: 'HUMAN_ACTIVE', agentId: 2, agent: '客服小周',
    lastMessageAt: ago(16), messages: [message('customer', '张女士', '想问一下这件衬衫的面料。', 17),
      message('agent', '客服小周', '您好，我帮您核对这款商品的成分信息。', 16)],
  };
  return { staff: { id: 1, name: '客服小林', online: true }, conversations: [lin, chen, wang, zhao, zhou, xu, zhang] };
}

export function createMockWorkbenchRepository(): WorkbenchRepository {
  const state = createFixtures();
  let nextMessageId = 1000;
  let nextTicketId = 302;
  let nextConversationId = 108;
  function find(id: number) {
    const row = state.conversations.find(row => row.id === id);
    if (!row) throw new WorkbenchError('NOT_FOUND', '这段会话已不存在，请重新选择。');
    return row;
  }
  function owned(row: WorkbenchConversation) {
    if (row.status !== 'HUMAN_ACTIVE' || row.agentId !== state.staff.id)
      throw new WorkbenchError('NOT_OWNER', '请先接入这段会话。');
  }
  function append(row: WorkbenchConversation, sender: WorkbenchMessage['sender'], content: string,
    kind: WorkbenchMessage['kind'] = 'text', imageUrl?: string) {
    const at = new Date().toISOString();
    row.messages.push({ id: nextMessageId++, sender, name: sender === 'agent' ? state.staff.name : row.customer,
      content, kind, createdAt: at, imageUrl });
    if (kind !== 'divider') row.lastMessageAt = at;
  }
  return {
    updateOrder(id, patch) { state.conversations.forEach(c => c.orders.forEach(o => { if (o.id === id) Object.assign(o, clone(patch)); })); },
    async completeTicket(id) {
      await delay();
      const ticket = state.conversations.flatMap(c => c.tickets).find(t => t.id === id);
      if (!ticket) throw new WorkbenchError('NOT_FOUND', '工单已不存在。');
      if (ticket.completion !== 'DONE') Object.assign(ticket, { completion: 'DONE', completedAt: new Date().toISOString(), completedBy: state.staff.name, revision: ticket.revision + 1 });
      return clone(ticket);
    },
    async load() { await delay(); return clone(state); },
    async setOnline(online) { await delay(80); state.staff.online = online; },
    markRead(id) { find(id).unread = false; },
    async claim(id) {
      await delay(); const row = find(id);
      if (!state.staff.online) throw new WorkbenchError('OFFLINE', '切换为在线后才能接入新会话。');
      if (row.status !== 'WAITING_USER') throw new WorkbenchError('ALREADY_CLAIMED', '这段会话已被接入，请查看最新接待状态。');
      row.status = 'HUMAN_ACTIVE'; row.agentId = state.staff.id; row.agent = state.staff.name; row.unread = false;
      append(row, 'system', '以上为 AI 自动回复 · 客服小林已接入', 'divider');
      return clone(row);
    },
    async close(id) {
      await delay(); const row = find(id); owned(row); row.status = 'CLOSED'; row.summary = undefined;
      append(row, 'system', '客服小林已完结本次会话', 'divider');
      return clone(row);
    },
    async reopen(id) {
      await delay(); const row = find(id);
      if (!state.staff.online) throw new WorkbenchError('OFFLINE', '切换为在线后才能重新发起会话。');
      if (row.status !== 'CLOSED') throw new WorkbenchError('NOT_CLOSED', '这段会话正在接待中。');
      const active = state.conversations.find(c => c.customerId === row.customerId && c.status !== 'CLOSED');
      if (active) throw new WorkbenchError('ACTIVE_EXISTS', '该客户已有进行中的会话，请先处理当前会话。');
      const next = clone(row); next.id = nextConversationId++; next.status = 'HUMAN_ACTIVE';
      next.timelineHistory = [...(row.timelineHistory || []), ...clone(row.messages)];
      next.agentId = state.staff.id; next.agent = state.staff.name; next.messages = []; next.tickets = []; next.summary = undefined;
      next.lastMessageAt = new Date().toISOString(); next.unread = false;
      next.history = [{ id: row.id, endedAt: row.lastMessageAt, agent: row.agent || 'AI 客服',
        summary: row.messages.filter(m => m.sender === 'customer').at(-1)?.content || '上一次咨询', messages: clone(row.messages) }, ...row.history];
      append(next, 'system', '客服小林发起了一次新的人工客服会话', 'divider');
      state.conversations.push(next); return clone(next);
    },
    async send(id, text, images) {
      await delay(); const row = find(id); owned(row);
      if (!text.trim() && !images.length) throw new WorkbenchError('EMPTY', '请填写回复内容。');
      if (text.trim()) append(row, 'agent', text.trim());
      images.forEach(url => append(row, 'agent', '图片', 'image', url));
      return clone(row);
    },
    async addCustomerMessage(id, text) {
      await delay(); const row = find(id);
      if (!text.trim()) throw new WorkbenchError('EMPTY', '请填写客户消息。');
      append(row, 'customer', text.trim()); return clone(row);
    },
    generate(id, signal, fail = false) {
      const row = find(id); owned(row);
      return new Promise((resolve, reject) => {
        if (signal.aborted) { reject(new DOMException('已取消', 'AbortError')); return; }
        const abort = () => { clearTimeout(timer); reject(new DOMException('已取消', 'AbortError')); };
        const timer = setTimeout(() => {
          signal.removeEventListener('abort', abort);
          if (fail) reject(new WorkbenchError('GENERATION_FAILED', 'AI 暂时未能生成回复，您可以直接手动回复。'));
          else resolve(row.suggestion || '您好，我是小林。我来帮您核实具体情况，请您补充需要处理的商品和问题。');
        }, 2300);
        signal.addEventListener('abort', abort, { once: true });
      });
    },
    async saveTicket(input, existing) {
      await delay(); const row = find(input.conversationId);
      if (!row.orders.some(o => o.id === input.orderId)) throw new WorkbenchError('ORDER_SCOPE', '请选择本次会话关联的订单。');
      if (!input.types.length || input.types.some(t => !Object.hasOwn(ticketTypeLabels, t)) || !input.description.trim())
        throw new WorkbenchError('INVALID_TICKET', '请选择诉求类型并填写诉求说明。');
      if (input.refundAmount && (!/^\d+(\.\d{1,2})?$/.test(input.refundAmount) || Number(input.refundAmount) <= 0))
        throw new WorkbenchError('INVALID_AMOUNT', '请填写大于 0 的金额，最多保留两位小数。');
      if (existing) {
        const ticket = row.tickets.find(t => t.id === existing.id);
        if (!ticket || ticket.orderId !== input.orderId) throw new WorkbenchError('NOT_FOUND', '工单关联不能修改。');
        if (ticket.revision !== existing.revision) throw new WorkbenchError('CONFLICT', '工单刚刚被修改，请重新打开后编辑。');
        Object.assign(ticket, clone(input), { types: [...new Set(input.types)], revision: ticket.revision + 1 });
        return clone(ticket);
      }
      const duplicate = row.tickets.find(t => t.orderId === input.orderId);
      if (duplicate) throw new WorkbenchError('TICKET_EXISTS', '该订单已有本次诉求记录，可以在原工单中继续补充。', duplicate.id);
      const ticket: WorkbenchTicket = { ...clone(input), types: [...new Set(input.types)],
        id: nextTicketId++, number: `CS${new Date().toISOString().slice(0, 10).replaceAll('-', '')}${String(nextTicketId).padStart(4, '0')}`,
        customerId: row.customerId, completion: 'PENDING', source: 'MANUAL', createdAt: new Date().toISOString(), revision: 1 };
      row.tickets.push(ticket); return clone(ticket);
    },
  };
}
