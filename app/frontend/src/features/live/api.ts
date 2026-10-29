export interface Reception {
  id: number; thread_id: number; user_id: number; customer_name: string;
  status: 'AI_ACTIVE' | 'WAITING_USER' | 'HUMAN_ACTIVE' | 'CLOSED';
  current_agent_id: number | null; agent_name: string | null;
  reception_epoch: number; revision: number; thread_revision?: number;
  started_at: string; last_message_at: string; closed_at: string | null;
  handoff_requested_at: string | null; consultation_summary: string | null;
}
export interface Staff { id: number; display_name: string; username: string; active: boolean; work_status: string }
export interface StoredMessage {
  id: number; conversation_id: number; thread_id: number; sender_type: string;
  sender_name: string; content: string; created_at: string;
  citations: KnowledgeSource[]; trace_id: string | null;
}
export interface KnowledgeSource { id: number; document_id: number; document_title: string; version_id: number; version: number; score: number; content: string }
export const STAFF_TOKEN = 'foundation-staff-token';
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
export function createApi(token: () => string | null, staff = false) {
  return async function request<T>(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST'): Promise<T> {
    const headers: Record<string, string> = {};
    if (token()) headers.Authorization = `Bearer ${token()}`;
    if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
    let response: Response;
    try { response = await fetch(path, { method, headers, body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body) }); }
    catch { throw new ApiError(0, 'NETWORK', '连接暂时中断，请稍后重试。'); }
    const value = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = typeof value.detail === 'string' ? value.detail : value.detail?.message;
      const fields = Array.isArray(value.detail?.errors) ? value.detail.errors.map((e: {message: string}) => e.message).join('；') : '';
      const error = new ApiError(response.status, value.detail?.code || 'REQUEST_FAILED', fields || message || (response.status === 422 ? '请检查填写内容。' : '操作未完成，请刷新后重试。'));
      if (staff && response.status === 401 && token()) window.dispatchEvent(new CustomEvent('foundation-session-expired', { detail: error.message }));
      throw error;
    }
    return value as T;
  };
}
export const staffApi = createApi(() => sessionStorage.getItem(STAFF_TOKEN), true);

export async function allPages<T>(api: ReturnType<typeof createApi>, path: string): Promise<T[]> {
  const result: T[] = [];
  for (let page = 1; ; page++) {
    const value = await api<{ items: T[]; total: number }>(`${path}${path.includes('?') ? '&' : '?'}page_size=100&page=${page}`);
    result.push(...value.items);
    if (!value.items.length || page * 100 >= value.total) return result;
  }
}
export async function readMessages(api: ReturnType<typeof createApi>, path: string, previous: StoredMessage[] = []) {
  const result = [...previous]; let cursor = previous.at(-1)?.id || 0;
  for (;;) {
    const page = await api<{ items: StoredMessage[]; has_more: boolean; next_cursor: number }>(`${path}?page_size=100&after_id=${cursor}`);
    result.push(...page.items);
    if (!page.has_more || page.next_cursor <= cursor) return result;
    cursor = page.next_cursor;
  }
}
