import type { TraceDetail, TraceNode } from '../../domain/traces';
import type { Trace } from './usePreviewStore';

// A separate in-memory adapter feeds the original AgentServe trace detail component.
// These fixtures are snapshots: editing today's prompts/knowledge must not rewrite past traces.
const cache = new Map<number, { detail: TraceDetail; payloads: Record<number, unknown> }>();
export function replyTrace(trace: Trace) {
  const existing = cache.get(trace.id);
  if (existing) return existing;
  const payloads: Record<number, unknown> = {};
  const captured = trace.conversationId >= 600 && trace.conversationId < 622;
  const business = trace.route === '订单查询';
  const knowledge = trace.sources.some(s => !['订单查询结果', '商品详情'].includes(s));
  const route = business ? 'business' : 'knowledge';
  const nodes: TraceNode[] = [];
  function node(name: string, type: string, location: string, snapshots: Record<string, unknown>, model = '', usage: Record<string, unknown> = {}) {
    const sequence = nodes.length + 1, id = trace.id * 100 + sequence;
    const parent = nodes.at(-1);
    nodes.push({ id, sequence, name, node_type: type, location, status: 'SUCCESS', model, attempt: 1,
      started_at: trace.createdAt, ended_at: trace.createdAt, latency_ms: type === 'llm.generate' ? 1280 : 16,
      parent_node_id: null, depends_on: parent ? [parent.id] : [], summary: { route }, sources: trace.sources,
      usage, error: null, payloads: Object.entries(snapshots).map(([kind,content],i) => {
        const payloadId = id * 10 + i; payloads[payloadId] = content;
        return { id: payloadId, kind, byte_size: new TextEncoder().encode(JSON.stringify(content)).length, status: 'READY', storage: 'inline' };
      }) });
  }
  if (captured) {
    node('接收客户消息', 'local.input', 'local', { input: { conversation_id: trace.conversationId, message: trace.question }, output: { query: trace.question } });
    node('判断处理路线', 'local.route', 'local', { input: { query: trace.question }, output: { route, intent: trace.route, need_context: true } });
    if (knowledge) {
      node('生成检索向量', 'ai.embed', 'remote_ai', { request: { model: 'text-embedding-v3', input: trace.question }, output: { dimensions: 1024 } }, 'text-embedding-v3');
      node('检索客服知识', 'search.vector', 'opensearch', { input: { query: trace.question, top_k: 5, score_threshold: 0.3 }, output: { documents: trace.sources } });
      node('重排序候选知识', 'ai.rerank', 'remote_ai', { request: { model: 'gte-rerank-v2', query: trace.question, documents: trace.sources }, output: { selected_sources: trace.sources } }, 'gte-rerank-v2');
    } else {
      node(business ? '查询订单信息' : '读取商品信息', 'business.tool', 'mysql',
        { input: { conversation_id: trace.conversationId, query: trace.question }, output: { sources: trace.sources } });
    }
    const usage = { prompt_tokens: trace.input, completion_tokens: trace.output, total_tokens: trace.input! + trace.output! };
    node('生成客服回复', 'llm.generate', 'remote_ai', {
      input: { query: trace.question, sources: trace.sources },
      request: { model: 'deepseek-chat', messages: [{ role: 'system', content: '根据当前上下文回答店铺客户，不确定时追问。' }, { role: 'user', content: trace.question }], context_sources: trace.sources },
      raw_response: { choices: [{ message: { role: 'assistant', content: trace.answer } }], usage },
      output: { reply: trace.answer },
    }, 'deepseek-chat', usage);
    node('保存回复', 'local.reply', 'local', { input: { reply: trace.answer }, output: { message_id: trace.id } });
  }
  const detail: TraceDetail = {
    id: trace.id, trace_id: `reply-${trace.id}`, conversation_id: trace.conversationId, user_id: 0,
    username: trace.customer, customer_name: trace.customer, query: trace.question, final_reply: trace.answer,
    kind: 'customer_message', route, intent: trace.route, status: 'COMPLETED', outcome: 'ANSWERED',
    model: captured ? 'deepseek-chat' : '', started_at: trace.createdAt, ended_at: trace.createdAt,
    latency_ms: nodes.reduce((sum,n) => sum+n.latency_ms,0), used_context: trace.sources.length > 0,
    fallback: false, handoff: false, handoff_reason: null, capture_complete: captured,
    capture_errors: captured ? [] : ['该回复未保存完整的节点参数快照。'], ai_used: true,
    ai_calls: captured ? { generate: 1, ...(knowledge ? { embed: 1, rerank: 1 } : {}) } : {},
    error: null, nodes, parent_trace_id: null, pending_action_id: null, question_message_id: trace.id-1,
    reply_message_id: trace.id, context_sources: { query: trace.question, sources: trace.sources },
    config_versions: captured ? { prompt: '通用接待 v1', retrieval: { top_k: 5, score_threshold: 0.3 } } : {},
    composition: [{ kind: 'AI 回复', text: trace.answer, sources: trace.sources }],
    related: [], audit: [],
  };
  const result = { detail, payloads }; cache.set(trace.id, result); return result;
}
