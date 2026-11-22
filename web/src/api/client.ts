export class ApiError extends Error {
  status: number;
  field: string | null;
  errorId: string | null;

  constructor(status: number, message: string, field: string | null, errorId: string | null) {
    super(errorId ? `${message} (ref ${errorId})` : message);
    this.name = "ApiError";
    this.status = status;
    this.field = field;
    this.errorId = errorId;
  }
}

let unauthorizedHandler: (() => void) | null = null;

/** Called on every 401 so the app can drop back to the login screen. */
export function onUnauthorized(fn: (() => void) | null): void {
  unauthorizedHandler = fn;
}

async function request(
  path: string,
  init: RequestInit & { json?: unknown } = {}
): Promise<Response> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...rest,
    headers: {
      Accept: "application/json",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.ok) return res;
  let body: { error?: string; error_id?: string | null; field?: string | null } = {};
  try {
    body = await res.json();
  } catch {
    // not JSON (proxy error page etc.)
  }
  if (res.status === 401) unauthorizedHandler?.();
  throw new ApiError(
    res.status,
    body.error ?? `Request failed (${res.status})`,
    body.field ?? null,
    body.error_id ?? null
  );
}

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const res = await request(path, init);
  return (await res.json()) as T;
}

export async function apiText(path: string): Promise<string> {
  const res = await request(path, { headers: { Accept: "text/plain" } });
  return res.text();
}
