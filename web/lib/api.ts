// Typed client for the Volunteer Ops public API.
// Works both server-side (SSR) and client-side. On the server a relative
// base has no host, so we fall back to an absolute internal base.

export interface Session {
  id: number;
  course_title: string;
  description: string;
  location: string;
  starts_at: string | null;
  ends_at: string | null;
  capacity: number | null;
  seats_available: boolean;
}

// Human-readable date/time for a session, e.g. "Sat 9 Aug · 10:00–12:00".
// Falls back to a friendly label when no date is scheduled.
export function formatWhen(
  starts_at: string | null,
  ends_at: string | null,
): string {
  if (!starts_at) return 'Flexible / ongoing';
  const start = new Date(starts_at);
  if (Number.isNaN(start.getTime())) return 'Flexible / ongoing';

  const date = start.toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
  const time = start.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  });

  if (ends_at) {
    const end = new Date(ends_at);
    if (!Number.isNaN(end.getTime())) {
      const endTime = end.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
      });
      return `${date} · ${time}–${endTime}`;
    }
  }
  return `${date} · ${time}`;
}

export interface RegisterInput {
  name: string;
  email: string;
  phone?: string;
}

export interface RegisterResult {
  status: string;
  waitlisted: boolean;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const PUBLIC_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '/api';

export function apiBase(): string {
  // In the browser we always use the (possibly relative) public base and let
  // the Next rewrite proxy forward it.
  if (typeof window !== 'undefined') return PUBLIC_BASE;
  // Server side: a relative path cannot be fetched, so use an absolute base.
  if (PUBLIC_BASE.startsWith('http')) return PUBLIC_BASE;
  return process.env.API_INTERNAL_BASE ?? 'http://localhost:8000/api';
}

export async function parseError(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (
      body &&
      typeof body === 'object' &&
      'detail' in body &&
      typeof (body as { detail: unknown }).detail === 'string'
    ) {
      return (body as { detail: string }).detail;
    }
  } catch {
    // fall through to generic message
  }
  return 'Something went wrong. Please try again.';
}

export async function getSessions(): Promise<Session[]> {
  const res = await fetch(`${apiBase()}/public/sessions`, {
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as Session[];
}

export async function getSession(id: number): Promise<Session | null> {
  const res = await fetch(`${apiBase()}/public/sessions/${id}`, {
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as Session;
}

export async function registerForSession(
  id: number,
  input: RegisterInput,
): Promise<RegisterResult> {
  const res = await fetch(`${apiBase()}/public/sessions/${id}/register`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as RegisterResult;
}

export async function verifyToken(token: string): Promise<RegisterResult> {
  const res = await fetch(`${apiBase()}/public/verify`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as RegisterResult;
}
