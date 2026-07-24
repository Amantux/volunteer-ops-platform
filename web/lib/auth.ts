// Authenticated client for the Volunteer Ops app surfaces.
// The opaque session token is the ONLY thing we persist (localStorage); no
// passwords or personal data are stored client-side.

import { ApiError, apiBase, parseError } from '@/lib/api';

export { ApiError };

const TOKEN_KEY = 'vop_session';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private-mode / storage-disabled: nothing else we can do here.
  }
}

export function clearToken(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Types (mirror the backend contract)
// ---------------------------------------------------------------------------
export interface Me {
  name: string;
  email: string;
  permissions: string[];
  has_volunteer_profile: boolean;
}

export interface MyShift {
  signup_id: number;
  status: string;
  waitlisted: boolean;
  event_title: string;
  role: string;
  starts_at: string | null;
  ends_at: string | null;
  location: string;
}

export interface EligibleRole {
  role_id: number;
  role: string;
  shift_id: number;
  starts_at: string | null;
  location: string;
  why_eligible: string;
}

export interface SignupResult {
  id: number;
  status: string;
  waitlisted: boolean;
}

export interface BoardSignup {
  signup_id: number;
  volunteer: string;
  status: string;
}

export interface BoardRole {
  role_id: number;
  role: string;
  filled: number;
  capacity: number;
  signups: BoardSignup[];
}

export interface BoardShift {
  shift_id: number;
  starts_at: string | null;
  ends_at: string | null;
  location: string;
  is_open: boolean;
  roles: BoardRole[];
}

export interface BoardEvent {
  event_id: number;
  title: string;
  kind: string;
  shifts: BoardShift[];
}

export interface UnderstaffedRole {
  role_id: number;
  role: string;
  shift_id: number;
  filled: number;
  capacity: number;
}

export interface Staffing {
  roles: number;
  capacity: number;
  filled: number;
  fill_rate: number;
  understaffed: UnderstaffedRole[];
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

// Plain POST for the pre-auth endpoints (no bearer token yet).
async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as T;
}

// Authenticated fetch: attaches the bearer token, throws ApiError on failure,
// and clears the stored token on a 401 so the UI can bounce to /login.
export async function authFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  headers.set('accept', 'application/json');
  if (token) headers.set('authorization', `Bearer ${token}`);

  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers,
    cache: 'no-store',
  });

  if (res.status === 401) {
    clearToken();
    throw new ApiError(401, await parseError(res));
  }
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res;
}

async function authGet<T>(path: string): Promise<T> {
  const res = await authFetch(path);
  return (await res.json()) as T;
}

async function authPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await authFetch(path, {
    method: 'POST',
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export function requestLogin(email: string): Promise<{ message: string }> {
  return postJson<{ message: string }>('/auth/request-login', { email });
}

export function login(token: string): Promise<{ token: string }> {
  return postJson<{ token: string }>('/auth/login', { token });
}

export function activate(
  token: string,
  password?: string,
): Promise<{ token: string }> {
  const body: { token: string; password?: string } = { token };
  if (password) body.password = password;
  return postJson<{ token: string }>('/auth/activate', body);
}

export function getMe(): Promise<Me> {
  return authGet<Me>('/auth/me');
}

// ---------------------------------------------------------------------------
// Volunteer scheduling
// ---------------------------------------------------------------------------
export function getMyShifts(): Promise<MyShift[]> {
  return authGet<MyShift[]>('/shifts/mine');
}

export function getEligible(): Promise<EligibleRole[]> {
  return authGet<EligibleRole[]>('/shifts/eligible');
}

export function signup(roleId: number): Promise<SignupResult> {
  return authPost<SignupResult>('/shifts/signup', { role_id: roleId });
}

export async function cancelSignup(signupId: number): Promise<void> {
  await authFetch(`/shifts/signups/${signupId}/cancel`, { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Coordinator
// ---------------------------------------------------------------------------
export function getBoard(): Promise<BoardEvent[]> {
  return authGet<BoardEvent[]>('/coordinator/board');
}

export function getStaffing(): Promise<Staffing> {
  return authGet<Staffing>('/coordinator/metrics/staffing');
}

export async function checkin(signupId: number): Promise<void> {
  await authFetch('/coordinator/checkin', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ signup_id: signupId }),
  });
}

export async function logHours(signupId: number, hours: number): Promise<void> {
  await authFetch('/coordinator/hours', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ signup_id: signupId, hours }),
  });
}
