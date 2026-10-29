export type Message = {
  id: number;
  sender_type: string;
  content: string;
  citations: { title: string; document_id: number; version_id: number }[];
  created_at: string;
};
export type Conversation = {
  id: number;
  account_id: number;
  account_name?: string;
  platform_code?: string;
  status: string;
  user_id: number;
  current_agent_id: number | null;
  handoff_reason: string | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly token?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function checkResponse(
  response: Response,
  token?: string,
): Promise<void> {
  if (response.ok) return;
  let detail = response.statusText;
  try {
    const value = (await response.json()).detail;
    detail = Array.isArray(value)
      ? value
          .map(
            (item: { loc?: string[]; msg?: string }) =>
              `${item.loc?.slice(1).join(".") || "参数"}：${item.msg || "格式错误"}`,
          )
          .join("；")
      : typeof value === "string"
        ? value
        : detail;
  } catch {
    /* use status text */
  }
  throw new ApiError(detail, response.status, token);
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method,
    headers,
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
  });
  await checkResponse(response, token);
  return response.json() as Promise<T>;
}
