export type TracePayload = { id: number; kind: string; byte_size: number; status: string; storage: string };
export type TraceNode = { id: number; sequence: number; name: string; node_type: string; location: string;
  status: string; model: string; attempt: number; started_at: string; ended_at: string | null; latency_ms: number;
  parent_node_id: number | null; depends_on: number[]; summary: Record<string, unknown>; sources: unknown[];
  usage: Record<string, unknown>; error: string | null; payloads: TracePayload[] };
export type TraceRow = { id: number; trace_id: string; conversation_id: number; user_id: number; username: string;
  customer_name: string; query: string; final_reply: string; kind: string; route: string; intent: string; status: string; outcome: string;
  model: string; started_at: string; ended_at: string | null; latency_ms: number; used_context: boolean;
  fallback: boolean; handoff: boolean; handoff_reason: string | null; capture_complete: boolean;
  capture_errors: string[]; ai_used: boolean; ai_calls: Record<string, number>; error: string | null;
  nodes: { id: number; name: string; type: string; location: string; status: string }[] };
export type TraceDetail = Omit<TraceRow, "nodes"> & { nodes: TraceNode[];
  parent_trace_id: string | null; pending_action_id: number | null; question_message_id: number | null;
  reply_message_id: number | null; context_sources: Record<string, unknown>; config_versions: Record<string, unknown>;
  composition: { kind: string; text: string; sources: unknown[] }[];
  related: { trace_id: string; kind: string; outcome: string }[];
  audit: { id: number; action: string; actor: string; created_at: string; detail: unknown }[] };
export const routes: Record<string, string> = { business: "业务查询", knowledge: "知识问答", hybrid: "业务与知识", clarify: "追问", human: "人工", chitchat: "问候" };
export const outcomes: Record<string, string> = { PROCESSING: "处理中", ANSWERED: "已回答（待客户反馈）", CLARIFY: "待补充信息",
  PENDING_CONFIRMATION: "待客户确认", HANDOFF: "已转人工", HUMAN_PENDING: "等待人工", HUMAN_ACTIVE: "人工处理中",
  ERROR: "执行失败", DONE: "动作已完成", CANCELLED: "客户取消动作", REJECTED: "动作被拒绝", UNCERTAIN: "动作结果不确定" };
export const locations: Record<string, string> = { local: "本地代码", mysql: "MySQL", opensearch: "OpenSearch", remote_ai: "远程 AI", http_api: "HTTP API" };
export const payloadLabels: Record<string, string> = { input: "输入参数", request: "实际业务请求", raw_response: "原始返回", output: "输出结果", error: "异常" };
export const json = (value: unknown) => JSON.stringify(value, null, 2);
export { formatLocalDateTime as time } from "./datetime";
