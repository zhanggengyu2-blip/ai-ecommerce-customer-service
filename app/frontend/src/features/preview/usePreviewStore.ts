import { computed, inject, reactive, ref, watch, type InjectionKey } from 'vue';
import type { WorkbenchContext } from '../workbench/useWorkbench';
import type { WorkbenchMessage, WorkbenchOrder } from '../workbench/types';

export const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));
export const now = () => new Date().toISOString();
export const daysAgo = (days: number) => new Date(Date.now() - days * 86400000).toISOString();
export function navigate(page: string, id?: number) { window.location.hash = `/${page}${id ? `?id=${id}` : ''}`; }
export interface KnowledgeDoc { id: number; categoryId: number; title: string; purpose: string; content: string; separator: string; length: number; overlap: number; start: string; end: string; enabled: boolean; chunks: string[]; updatedAt: string; author: string; previous?: Omit<KnowledgeDoc, 'previous'> }
export interface Product { id: number; groupId: number; name: string; variant: string; price: number; stock: number; reserved: number; active: boolean; thumbnail: WorkbenchOrder['thumbnail']; imageUrl?: string }
export interface ShopOrder extends WorkbenchOrder { customerId: number; customer: string; productId: number; stage: 'UNPAID'|'PAID'|'SHIPPED'|'DELIVERED'|'CANCELLED'|'REFUNDING'|'REFUNDED'; createdAt: string }
export interface Refund { id: number; orderId: number; amount: number; reason: string; status: 'REQUESTED'|'APPROVED'|'REJECTED'|'RECEIVED'|'COMPLETED'; original: ShopOrder['stage']; tracking: string; createdAt: string }
export interface Trace { id: number; conversationId: number; customer: string; question: string; answer: string; route: string; result: string; input: number|null; output: number|null; createdAt: string; sources: string[] }
export interface HistoryRow { id: number; customer: string; agent: string; summary: string; startedAt: string; endedAt: string; human: boolean; requested: boolean; messages: WorkbenchMessage[]; orders: WorkbenchOrder[] }
export function createPreviewStore(wb: WorkbenchContext) {
  const recordId = ref<number | null>(null), traceId = ref<number | null>(null);
  const openRecord = (id: number) => { recordId.value = id; };
  const openTrace = (id: number) => { traceId.value = id; };
  const categories = ref([{ id: 1, name: '平台政策', description: '淘宝平台的通用交易与售后规则' }, { id: 2, name: '店铺政策', description: '青禾服饰的服务承诺及售后补充' }, { id: 3, name: '售后服务', description: '退换货办理、物流问题与沟通指引' }, { id: 4, name: '商品与活动', description: '商品业务说明、补货与活动提醒' }]);
  const docs = ref<KnowledgeDoc[]>([
    { id: 1, categoryId: 1, title: '服装售后咨询指引', purpose: '回答退货时效、适用条件及需要核实的订单信息。', content: '# 退货咨询\n先核实订单、收货时间、商品状态和客户具体诉求，再按当前适用政策说明办理方式。不要仅凭历史聊天中的承诺判断本次订单。\n\n# 退款进度\n退款时间与平台及当前售后状态有关。查询实际进度后再回答，不承诺未经确认的到账时间。', separator: '\n\n', length: 500, overlap: 50, start: '', end: '', enabled: true },
    { id: 2, categoryId: 2, title: '青禾服饰售后补充', purpose: '说明本店换码前的核实事项与商品包装要求。', content: '# 换码前确认\n请核实订单与需要换货的商品、颜色和目标尺码。先查询当前库存，未核实前不要承诺一定有货。\n\n# 办理说明\n引导客户在订单售后入口提出申请；遇到特殊诉求请转人工客服，由客服确认并回复。', separator: '\n\n', length: 500, overlap: 50, start: '', end: '', enabled: true },
    { id: 3, categoryId: 3, title: '人工接待等待话术', purpose: '客户提出人工服务、等待接入超过 300 秒时使用。', content: '# 等待人工接入\n很抱歉让您久等了，您的问题已记录，客服会在接入后继续为您处理。您可以先补充订单和具体诉求，避免重复说明。\n\n# 修改收货地址\n先查询是否发货；已发货时不要直接承诺修改成功，需人工核实后反馈。', separator: '\n\n', length: 500, overlap: 50, start: '', end: '', enabled: true },
    { id: 4, categoryId: 4, title: '长裤补货提醒', purpose: '回答休闲直筒长裤缺码时的补货咨询。', content: '# 补货说明\n休闲直筒长裤部分尺码正在补货，预计下月到货，具体以实际入库为准。请先核实客户的颜色和尺码，不接受未经确认的到货保证。', separator: '\n\n', length: 500, overlap: 50, start: '', end: '', enabled: true },
    { id: 5, categoryId: 4, title: '上期活动说明', purpose: '已结束的历史活动，保留用于查阅。', content: '上期活动已结束。本篇仅保留记录，不参与当前知识检索。', separator: '\n\n', length: 500, overlap: 50, start: '', end: daysAgo(2), enabled: true },
  ].map(d => ({ ...d, chunks: splitText(d.content, d.length, d.overlap, d.separator), updatedAt: daysAgo(1), author: '客服小林' })));
  const retrieval = reactive({ topK: 5, score: '0.30' });
  const aiEnabled = ref(true);
  const models = reactive([
    { role: '对话推理', provider: 'DeepSeek', model: 'deepseek-chat', configured: true, tail: '7F2A' },
    { role: '向量化', provider: '百炼千问', model: 'text-embedding-v3', configured: true, tail: '4B8C' },
    { role: '重排序', provider: '百炼千问', model: 'gte-rerank-v2', configured: true, tail: '4B8C' },
  ]);
  const prompts = ref([
    { id: 1, name: '通用接待', scene: '商品咨询、信息不完整时的追问与日常接待', content: '你是青禾服饰的在线客服。\n目标：理解客户诉求，准确、简洁地提供帮助。\n要求：优先核实事实。缺少订单或商品信息时先追问；需要当前状态时查询实时信息。使用检索到的有效知识，不编造库存、退款时间或处理结果。\n语气：耐心、自然，一次只询问必要的信息。' },
    { id: 2, name: '售后沟通', scene: '退款、退货退款、换货及其他售后诉求', content: '先确认具体订单、商品、数量和售后诉求。\n根据当前适用知识及订单状态说明办理方式。\n需要人工确认或无法确定的情况，记录已知信息并请求人工帮助，不替客服作出未经授权的承诺。' },
    { id: 3, name: '人工接待等待', scene: '已请求人工，等待超过 300 秒', content: '客户正在等待人工接入。\n根据人工等待的知识指引表达理解和安抚，告知诉求已记录。\n可以请客户补充必要信息，不承诺具体接入时间，不重复创建人工请求。' },
  ]);
  const accounts = ref([{ id: 1, name: '客服小林', login: 'lin', avatar: '', enabled: true, online: true, lastLogin: now() }, { id: 2, name: '客服小周', login: 'zhou', avatar: '', enabled: true, online: true, lastLogin: daysAgo(0) }, { id: 3, name: '客服小陈', login: 'chen', avatar: '', enabled: true, online: false, lastLogin: daysAgo(1) }]);
  const greeting = reactive({ enabled: false, text: '您好，欢迎来到青禾服饰！我是 AI 客服，请问有什么可以帮您？' });
  const products = ref<Product[]>([
    { id: 1, groupId: 1, name: '休闲直筒长裤', variant: '黑色 / M 码', price: 129, stock: 28, reserved: 0, active: true, thumbnail: 'trousers' },
    { id: 2, groupId: 2, name: '柔软圆领针织衫', variant: '燕麦色 / 均码', price: 189, stock: 46, reserved: 0, active: true, thumbnail: 'knit' },
    { id: 3, groupId: 3, name: '基础款牛津纺衬衫', variant: '浅蓝色 / L 码', price: 159, stock: 19, reserved: 1, active: true, thumbnail: 'shirt' },
    { id: 5, groupId: 1, name: '休闲直筒长裤', variant: '黑色 / L 码', price: 129, stock: 10, reserved: 0, active: true, thumbnail: 'trousers' },
    { id: 6, groupId: 3, name: '基础款牛津纺衬衫', variant: '浅蓝色 / M 码', price: 159, stock: 10, reserved: 0, active: true, thumbnail: 'shirt' },
    { id: 4, groupId: 4, name: '秋日宽松针织衫', variant: '浅灰色 / 均码', price: 219, stock: 0, reserved: 0, active: false, thumbnail: 'knit' },
  ]);
  const customers = ref([{ id: 1001, name: '林女士', phone: '138****6028', address: '上海市徐汇区', note: '偏好自然简洁的服装' }, { id: 1002, name: '陈先生', phone: '139****1036', address: '浙江省杭州市', note: '' }, { id: 1003, name: '王女士', phone: '136****8021', address: '江苏省南京市', note: '' }, { id: 1004, name: '赵先生', phone: '137****0027', address: '浙江省宁波市', note: '' }, { id: 1005, name: '周女士', phone: '135****1008', address: '上海市浦东新区', note: '' }, { id: 1006, name: '许先生', phone: '139****3056', address: '江苏省苏州市', note: '' }]);
  const orders = ref<ShopOrder[]>([]);
  const payments = ref<{ id: number; orderId: number; amount: number; status: string; createdAt: string }[]>([]);
  const refunds = ref<Refund[]>([]);
  const inventory = ref([{ id: 1, productId: 1, change: 30, after: 30, reason: '商品入库', actor: '客服小周', createdAt: daysAgo(4) }, { id: 2, productId: 1, change: -2, after: 28, reason: '订单预占', actor: '系统', createdAt: daysAgo(3) }]);
  const businessEvents = ref<{ id: number; label: string; createdAt: string }[]>([]);
  watch(wb.loading, loading => {
    if (loading || orders.value.length) return;
    const seen = new Set<number>();
    wb.conversations.value.forEach(c => c.orders.forEach(o => {
      if (seen.has(o.id)) return; seen.add(o.id);
      orders.value.push({ ...copy(o), customerId: c.customerId, customer: c.customer, productId: o.thumbnail === 'trousers' ? 1 : o.thumbnail === 'knit' ? 2 : 3,
        stage: o.status === '待发货' ? 'PAID' : o.status === '已签收' ? 'DELIVERED' : 'SHIPPED', createdAt: o.paidAt });
      payments.value.push({ id: 500 + o.id, orderId: o.id, amount: o.amount, status: '支付成功', createdAt: o.paidAt });
    }));
  }, { immediate: true });
  function event(label: string) { businessEvents.value.push({ id: Date.now(), label, createdAt: now() }); }
  function syncOrder(order: ShopOrder) { const labels: Record<ShopOrder['stage'], string> = { UNPAID: '待付款', PAID: '待发货', SHIPPED: '运输中', DELIVERED: '已签收', CANCELLED: '已取消', REFUNDING: '售后处理中', REFUNDED: '已退款' }; order.status = labels[order.stage]; wb.updateOrder(order.id, { status: order.status, carrier: order.carrier, tracking: order.tracking }); }
  function stock(product: Product, change: number, reason: string) { if (product.stock + change < 0) throw new Error('可用库存不足。'); product.stock += change; inventory.value.unshift({ id: inventory.value.reduce((id, row) => Math.max(id, row.id + 1), Date.now()), productId: product.id, change, after: product.stock, reason, actor: wb.staff.name, createdAt: now() }); }
  function orderAction(id: number, action: string, extra = '') {
    const o = orders.value.find(o => o.id === id); if (!o) throw new Error('订单不存在。');
    const p = products.value.find(p => p.id === o.productId)!;
    if (action === 'pay') { if (o.stage !== 'UNPAID') throw new Error('当前订单不能支付。'); o.stage = 'PAID'; o.paidAt = now(); payments.value.unshift({ id: Date.now(), orderId: id, amount: o.amount, status: '支付成功', createdAt: now() }); }
    else if (action === 'ship') { if (o.stage !== 'PAID') throw new Error('仅待发货订单可以发货。'); if (!extra.trim()) throw new Error('请填写快递单号。'); if (orders.value.some(x => x.id !== id && x.tracking === extra.trim())) throw new Error('快递单号已使用。'); o.stage = 'SHIPPED'; o.carrier = '顺丰速运'; o.tracking = extra.trim(); p.reserved = Math.max(0, p.reserved - o.quantity); }
    else if (action === 'cancel') { if (!['UNPAID','PAID'].includes(o.stage)) throw new Error('当前订单不能取消。'); const paid = o.stage === 'PAID'; stock(p, o.quantity, '取消订单释放库存'); p.reserved = Math.max(0, p.reserved - o.quantity); o.stage = 'CANCELLED'; if (paid) { const pay = payments.value.find(x => x.orderId === id); if (pay) pay.status = '已退款'; refunds.value.unshift({ id: Date.now(), orderId: id, amount: o.amount, reason: '已付款订单取消', status: 'COMPLETED', original: 'PAID', tracking: '', createdAt: now() }); } }
    else if (action === 'refund') { if (!['PAID','SHIPPED','DELIVERED'].includes(o.stage)) throw new Error('当前订单不能申请退款。'); if (!extra.trim()) throw new Error('请填写退款原因。'); refunds.value.unshift({ id: Date.now(), orderId: id, amount: o.amount, reason: extra.trim(), status: 'REQUESTED', original: o.stage, tracking: '', createdAt: now() }); o.stage = 'REFUNDING'; }
    else if (action === 'deliver') { if (o.stage !== 'SHIPPED') throw new Error('仅运输中订单可以签收。'); o.stage = 'DELIVERED'; }
    else throw new Error('不支持的操作。');
    syncOrder(o); event(({ pay: '订单支付', ship: '订单发货', cancel: '取消订单', refund: '申请退款', deliver: '确认签收' } as Record<string,string>)[action]);
  }
  function refundAction(id: number, action: string, tracking = '') {
    const r = refunds.value.find(r => r.id === id); if (!r) throw new Error('售后记录不存在。'); const o = orders.value.find(o => o.id === r.orderId)!; const p = products.value.find(p => p.id === o.productId)!;
    if (action === 'approve' && r.status === 'REQUESTED') r.status = 'APPROVED';
    else if (action === 'reject' && r.status === 'REQUESTED') { r.status = 'REJECTED'; o.stage = r.original; }
    else if (action === 'receive' && r.status === 'APPROVED' && ['SHIPPED','DELIVERED'].includes(r.original)) { if (!tracking.trim()) throw new Error('请填写退货快递单号。'); r.tracking = tracking.trim(); r.status = 'RECEIVED'; stock(p, o.quantity, '退货收货入库'); }
    else if (action === 'complete' && (r.status === 'RECEIVED' || (r.status === 'APPROVED' && r.original === 'PAID'))) { r.status = 'COMPLETED'; o.stage = 'REFUNDED'; const pay = payments.value.find(x => x.orderId === o.id); if (pay) pay.status = '已退款'; if (r.original === 'PAID') { stock(p, o.quantity, '未发货退款释放库存'); p.reserved = Math.max(0, p.reserved - o.quantity); } }
    else throw new Error('当前状态不能执行此操作。');
    syncOrder(o); event(({ approve: '同意退款', reject: '拒绝退款', receive: '退货收货', complete: '完成退款' } as Record<string,string>)[action]);
  }
  function createOrder(customerId: number, productId: number, quantity: number) { const c = customers.value.find(x => x.id === customerId); const p = products.value.find(x => x.id === productId); if (!c || !p || !p.active || !Number.isInteger(quantity) || quantity < 1) throw new Error('请选择客户、在售商品和正确的数量。'); if (p.stock < quantity) throw new Error('商品库存不足。'); stock(p, -quantity, '订单预占'); p.reserved += quantity; const id = Date.now(); orders.value.unshift({ id, number: `TB${id}`, customerId, customer: c.name, productId, product: p.name, variant: p.variant, quantity, amount: Math.round(p.price * quantity * 100) / 100, thumbnail: p.thumbnail, imageUrl: p.imageUrl, status: '待付款', stage: 'UNPAID', paidAt: '', createdAt: now(), receiver: `${c.name} · ${c.phone}`, address: c.address, carrier: '尚未发货', tracking: '—' }); event('创建订单'); }
  const historical = ref<HistoryRow[]>(Array.from({ length: 22 }, (_, i) => {
    const id = 600 + i, human = i % 3 === 0, question = ['这款衬衫有尺码表吗？','我的订单发货了吗？','想退货，请问怎么申请？','针织衫还会补货吗？'][i % 4];
    const customer = ['吴女士','李先生','唐女士','刘女士','孙先生'][i % 5]; const answer = ['您好，可以参考商品详情中的尺码表，也可以告诉我您的具体尺寸。','您好，已帮您查询，包裹正在运输中，请留意物流更新。','您好，请先提供需要售后的订单，我帮您核实具体情况。','您好，部分尺码正在补货，具体到货时间以实际入库为准。'][i % 4];
    const start = new Date(Date.now() - (i % 7) * 86400000 - (i + 1) * 3600000).toISOString();
    return { id, customer, agent: human ? '客服小周' : 'AI 客服', summary: ['客户咨询衬衫尺码，需参考尺码表确认。','客户查询发货进度，包裹正在运输中。','客户咨询退货申请，需要核实具体订单。','客户咨询针织衫补货，部分尺码待到货。'][i % 4], startedAt: start, endedAt: new Date(Date.parse(start) + 600000).toISOString(), human, requested: human,
      messages: [{ id: id*10, sender: 'customer', name: customer, kind: 'text', content: question, createdAt: start }, { id: id*10+1, sender: 'ai', name: 'AI 客服', kind: 'text', content: answer, createdAt: start }, ...(human ? [{ id: id*10+2, sender: 'agent' as const, name: '客服小周', kind: 'text' as const, content: '您好，我已接入，接下来由我协助您处理。', createdAt: start }] : [])], orders: [] };
  }));
  const histories = computed<HistoryRow[]>(() => [...historical.value, ...wb.conversations.value.filter(c => c.status === 'CLOSED').map(c => ({ id: c.id, customer: c.customer, agent: c.agent || 'AI 客服', summary: c.summary || '待生成摘要', startedAt: c.messages[0]?.createdAt || c.lastMessageAt, endedAt: c.lastMessageAt, human: c.agentId !== null, requested: c.agentId !== null, messages: c.messages, orders: c.orders })), ...wb.conversations.value.flatMap(c => c.history.map(h => ({ id: h.id, customer: c.customer, agent: h.agent, summary: h.summary, startedAt: h.messages[0]?.createdAt || h.endedAt, endedAt: h.endedAt, human: true, requested: true, messages: h.messages, orders: c.orders })))].filter((h, i, all) => all.findIndex(x => x.id === h.id) === i).sort((a,b) => Date.parse(b.endedAt)-Date.parse(a.endedAt)));
  const traceSessions = computed(() => [...histories.value,...wb.conversations.value.filter(c=>c.status!=='CLOSED').map(c=>({id:c.id,customer:c.customer,summary:c.summary||'',human:c.agentId!==null,messages:c.messages}))]);
  const traces = computed<Trace[]>(() => traceSessions.value.flatMap(h => h.messages.filter(m => m.sender === 'ai').map(m => ({ id: m.id, conversationId: h.id, customer: h.customer, question: h.messages.filter(x => x.sender === 'customer' && x.id < m.id).at(-1)?.content || h.summary, answer: m.content, route: h.summary.includes('退') ? '售后咨询' : h.summary.includes('发货') ? '订单查询' : '知识问答', result: h.human ? '请求人工' : '已回复', input: h.id >= 600 ? 860 + h.id % 80 : null, output: h.id >= 600 ? 60 + h.id % 25 : null, createdAt: m.createdAt, sources: h.summary.includes('退') ? ['服装售后咨询指引','青禾服饰售后补充'] : h.summary.includes('补货') ? ['长裤补货提醒'] : h.summary.includes('发货') || h.summary.includes('快递') ? ['订单查询结果'] : ['商品详情'] }))));
  const feedback = computed(() => traces.value.filter(t => t.id % 3 === 0).map(t => ({ ...t, rating: t.id % 4 === 0 ? '踩' : '赞', reason: t.id % 4 === 0 ? '希望补充更具体的办理步骤' : '回答清晰，解决了疑问' })));
  const tickets = computed(() => wb.conversations.value.flatMap(c => c.tickets));
  const effectiveDocs = computed(() => docs.value.filter(d => isEffective(d)));
  function publish(input: Omit<KnowledgeDoc, 'id'|'updatedAt'|'author'|'chunks'|'previous'>, id?: number) { if (!input.title.trim() || !input.content.trim()) throw new Error('请填写标题和知识正文。'); if (!categories.value.some(c => c.id === input.categoryId)) throw new Error('请选择知识库。'); if (!Number.isInteger(input.length) || input.length < 100 || input.length > 4000 || !Number.isInteger(input.overlap) || input.overlap < 0 || input.overlap >= input.length) throw new Error('分段长度为 100–4000，重叠长度应小于分段长度。'); if (input.start && input.end && Date.parse(input.start) >= Date.parse(input.end)) throw new Error('失效时间须晚于生效时间。');
    const existing = docs.value.find(d => d.id === id); const previous = existing ? copy(existing) : undefined; if (previous) delete previous.previous;
    const next: KnowledgeDoc = { ...copy(input), id: id || Date.now(), updatedAt: now(), author: wb.staff.name, chunks: splitText(input.content,input.length,input.overlap,input.separator), purpose: input.purpose.trim() || `用于回答「${input.title.trim()}」涉及的客户问题。`, previous };
    if (existing) Object.assign(existing, next); else docs.value.unshift(next); return next;
  }
  return { recordId, traceId, openRecord, openTrace, wb, categories, docs, retrieval, models, aiEnabled, prompts, accounts, greeting, products, customers, orders, payments, refunds, inventory, businessEvents, histories, traces, feedback, tickets, effectiveDocs, publish, stock, createOrder, orderAction, refundAction, event };
}
export function isEffective(doc: KnowledgeDoc) { const t = Date.now(); return doc.enabled && (!doc.start || Date.parse(doc.start) <= t) && (!doc.end || Date.parse(doc.end) > t); }
export function knowledgeStatus(doc: KnowledgeDoc) { return !doc.enabled ? '已停用' : doc.end && Date.parse(doc.end) <= Date.now() ? '已过期' : doc.start && Date.parse(doc.start) > Date.now() ? '未生效' : '已发布'; }
export function splitText(text: string, length: number, overlap: number, separator: string) { if (length < 1 || overlap < 0 || overlap >= length) return []; const chunks: string[] = []; const parts = separator ? text.split(separator.replaceAll('\\n','\n')) : [text]; for (const part of parts) { let start = 0; while (start < part.length && chunks.length < 500) { const end = Math.min(start + length, part.length); const segment = part.slice(start,end).trim(); if (segment) chunks.push(segment); if (end === part.length) break; start = end - overlap; } } return chunks; }
export type PreviewStore = ReturnType<typeof createPreviewStore>;
export const PreviewKey: InjectionKey<PreviewStore> = Symbol('preview');
export function usePreview() { const store = inject(PreviewKey); if (!store) throw new Error('缺少预览上下文'); return store; }
