// Kiosk contract helpers.
//
// Two very different callers live here:
//   * Admin management (`/api/admin/kiosks…`) goes through `authFetch`, so the
//     Bearer session token is attached and a 401 bounces to /login.
//   * The public display + its interactions (`/api/kiosk/{token}…`) use plain
//     `fetch` with NO auth header — the opaque token in the URL is the only
//     capability. These must never leak the admin session token.

import { apiBase, ApiError, parseError } from '@/lib/api';
import { authFetch } from '@/lib/auth';

// ---------------------------------------------------------------------------
// Shared vocabulary
// ---------------------------------------------------------------------------

// The panel kinds a kiosk can show, in the order the admin arranges them.
export type PanelType =
  | 'schedule'
  | 'checkin'
  | 'tasks'
  | 'fyi'
  | 'roster'
  | 'camera';

export const PANEL_TYPES: PanelType[] = [
  'schedule',
  'checkin',
  'tasks',
  'fyi',
  'roster',
  'camera',
];

// How a kiosk behaves. `display` is read-only signage; `shared` accepts taps
// (check-in, task toggles) from whoever is standing at the tablet.
export type KioskMode = 'display' | 'shared';

// A single configured panel entry (what the admin edits and PATCHes back).
// `fyi` panels carry title + text; the others are self-resolving on the server.
export interface PanelConfig {
  type: PanelType;
  title?: string;
  text?: string;
}

// ---------------------------------------------------------------------------
// Admin surface (authenticated)
// ---------------------------------------------------------------------------

export interface Kiosk {
  id: number;
  name: string;
  token: string;
  mode: KioskMode;
  program_id: number | null;
  location: string | null;
  panels: PanelConfig[];
  is_active: boolean;
}

export interface KioskTask {
  id: number;
  label: string;
  sort_order: number;
}

async function authGet<T>(path: string): Promise<T> {
  const res = await authFetch(path);
  return (await res.json()) as T;
}

async function authSend<T>(
  path: string,
  method: 'POST' | 'PATCH',
  body: unknown,
): Promise<T> {
  const res = await authFetch(path, {
    method,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  return (await res.json()) as T;
}

export function listKiosks(): Promise<Kiosk[]> {
  return authGet<Kiosk[]>('/admin/kiosks');
}

export interface KioskCreateInput {
  name: string;
  mode: KioskMode;
  program_id?: number;
  location?: string;
  panels?: PanelConfig[];
}

export function createKiosk(input: KioskCreateInput): Promise<{ id: number }> {
  return authSend<{ id: number }>('/admin/kiosks', 'POST', input);
}

// Partial update — send only the fields being changed (name/mode/location/
// program_id/panels/is_active).
export interface KioskPatch {
  name?: string;
  mode?: KioskMode;
  location?: string;
  program_id?: number;
  panels?: PanelConfig[];
  is_active?: boolean;
}

export function patchKiosk(
  id: number,
  patch: KioskPatch,
): Promise<{ id: number }> {
  return authSend<{ id: number }>(`/admin/kiosks/${id}`, 'PATCH', patch);
}

export function listKioskTasks(id: number): Promise<KioskTask[]> {
  return authGet<KioskTask[]>(`/admin/kiosks/${id}/tasks`);
}

export function createKioskTask(
  id: number,
  input: { label: string; sort_order?: number },
): Promise<{ id: number }> {
  return authSend<{ id: number }>(`/admin/kiosks/${id}/tasks`, 'POST', input);
}

// ---------------------------------------------------------------------------
// Public display surface (NO auth — the URL token is the capability)
// ---------------------------------------------------------------------------

export interface DisplaySignup {
  signup_id: number;
  name: string;
  role: string;
  starts_at: string | null;
  checked_in: boolean;
}

export interface DisplayTask {
  id: number;
  label: string;
  done: boolean;
}

// Resolved panels the display renders. Discriminated on `type`.
export type ResolvedPanel =
  | { type: 'fyi'; title: string; text: string }
  | { type: 'schedule'; signups: DisplaySignup[] }
  | { type: 'checkin'; signups: DisplaySignup[] }
  | { type: 'roster'; signups: DisplaySignup[] }
  | { type: 'tasks'; tasks: DisplayTask[] }
  | { type: 'camera'; status: 'not_configured'; note: string };

export interface KioskDisplayPayload {
  name: string;
  mode: KioskMode;
  panels: ResolvedPanel[];
}

// Plain (unauthenticated) GET/POST against the token endpoints. We deliberately
// do NOT go through authFetch so no Bearer header is ever attached.
async function publicGet<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as T;
}

async function publicPost(path: string, body?: unknown): Promise<void> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: 'POST',
    headers: body
      ? { 'content-type': 'application/json', accept: 'application/json' }
      : { accept: 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
    cache: 'no-store',
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

export function getKioskDisplay(token: string): Promise<KioskDisplayPayload> {
  return publicGet<KioskDisplayPayload>(
    `/kiosk/${encodeURIComponent(token)}`,
  );
}

export function kioskCheckin(token: string, signupId: number): Promise<void> {
  return publicPost(`/kiosk/${encodeURIComponent(token)}/checkin`, {
    signup_id: signupId,
  });
}

export function kioskToggleTask(token: string, taskId: number): Promise<void> {
  return publicPost(
    `/kiosk/${encodeURIComponent(token)}/tasks/${taskId}/toggle`,
  );
}
