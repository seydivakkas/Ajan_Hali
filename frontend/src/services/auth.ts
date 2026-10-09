/** Cookie-based localhost API session. CSRF stays in JS memory, never localStorage. */
export interface SessionInfo {
  authenticated: boolean;
  mode: 'local' | 'session' | 'workspace';
  workspace_id?: string | null;
  username: string;
  role: 'ADMIN' | 'DESIGNER' | 'OPERATOR';
  csrf_token: string | null;
}

const base = import.meta.env.VITE_API_URL || '';
let csrfToken: string | null = null;

export async function fetchSession(): Promise<SessionInfo> {
  const res = await fetch(`${base}/api/v1/auth/session`, { credentials: 'include' });
  if (!res.ok) throw new Error('AUTH_REQUIRED');
  const data: SessionInfo = await res.json();
  csrfToken = data.csrf_token;
  return data;
}

export async function login(username: string, password: string): Promise<SessionInfo> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(res.status === 401 ? 'Kullanıcı adı veya parola hatalı.' : 'Oturum açılamadı.');
  const data: SessionInfo = await res.json();
  csrfToken = data.csrf_token;
  return data;
}

export async function logout(): Promise<void> {
  await apiFetch(`${base}/api/v1/auth/logout`, { method: 'POST' });
  csrfToken = null;
}

/** Attach per-session CSRF to every state-changing API call. */
export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const method = (init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers.set('X-CSRF-Token', csrfToken);
  }
  return fetch(input, { ...init, credentials: 'include', headers });
}
