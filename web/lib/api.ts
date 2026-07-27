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

export interface OpportunityShift {
  shift_id: number;
  starts_at: string;
  ends_at: string;
  location: string;
  open_roles: number;
}

export interface Opportunity {
  event_id: number;
  title: string;
  description: string;
  kind: string;
  next_shift_at: string | null;
  location: string;
  shift_count: number;
  shifts: OpportunityShift[];
}

export interface CalendarItem {
  type: 'training' | 'opportunity';
  id: number;
  title: string;
  starts_at: string;
  ends_at: string | null;
  location: string;
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

export async function getOpportunities(): Promise<Opportunity[]> {
  const res = await fetch(`${apiBase()}/public/opportunities`, {
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as Opportunity[];
}

export async function getCalendar(): Promise<CalendarItem[]> {
  const res = await fetch(`${apiBase()}/public/calendar`, {
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as CalendarItem[];
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

// ---------------------------------------------------------------------------
// Donations — public (donor-facing) surface. No auth: the single-tenant org is
// resolved server-side. The server owns all money state; the client persists
// nothing before submit, and only the opaque capability token afterwards.
// ---------------------------------------------------------------------------
export type DonationKind = 'one_time' | 'recurring';

export interface CampaignDesignation {
  code: string;
  label: string;
}

export interface CampaignProgress {
  raised_minor_units: number;
  goal_minor_units: number;
  currency: string;
}

export interface PublicCampaign {
  slug: string;
  title: string;
  description: string;
  currency: string;
  suggested_amounts: number[]; // minor units
  designations: CampaignDesignation[];
  // Present only when the org opted into publishing aggregate progress.
  progress: CampaignProgress | null;
}

export interface CreateDonationInput {
  campaign_slug: string;
  amount_minor_units: number;
  kind: DonationKind;
  donor_name: string;
  donor_email: string;
  is_anonymous: boolean;
  designation_code: string;
  consent_marketing: boolean;
  // Anti-bot token (e.g. Turnstile). Empty string is accepted in dev.
  bot_token: string;
}

export interface CreateDonationResult {
  donation_id: string;
  token: string;
  status: string;
}

export type DonationStatusValue =
  | 'pending'
  | 'processing'
  | 'succeeded'
  | 'failed'
  | string;

// Poll target. Deliberately carries NO donor data — only what the flow needs to
// redirect to the hosted checkout and render the return page.
export interface DonationStatus {
  status: DonationStatusValue;
  checkout_url: string | null;
  amount_minor_units: number;
  currency: string;
}

// A missing / unpublished campaign 404s — surfaced as null so the route can show
// a friendly empty state; any other failure throws so the caller can degrade.
export async function getCampaign(slug: string): Promise<PublicCampaign | null> {
  const res = await fetch(`${apiBase()}/campaigns/${encodeURIComponent(slug)}`, {
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as PublicCampaign;
}

export async function createDonation(
  input: CreateDonationInput,
): Promise<CreateDonationResult> {
  const res = await fetch(`${apiBase()}/public/donations`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as CreateDonationResult;
}

export async function getDonationStatus(token: string): Promise<DonationStatus> {
  const res = await fetch(
    `${apiBase()}/public/donations/status?token=${encodeURIComponent(token)}`,
    { cache: 'no-store', headers: { accept: 'application/json' } },
  );
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as DonationStatus;
}

// ---------------------------------------------------------------------------
// CMS site builder — block schema (shared by the public renderer and the
// admin editor). This is the render-shape: html/embed content arrives under
// `safe_html` / `raw_html` (see the round-trip note in <PageBlocks>).
// ---------------------------------------------------------------------------
export interface HeadingBlock {
  type: 'heading';
  level: number;
  text: string;
}
export interface ParagraphBlock {
  type: 'paragraph';
  html: string;
}
export interface ImageBlock {
  type: 'image';
  url: string;
  alt: string;
}
export interface ButtonBlock {
  type: 'button';
  label: string;
  href: string;
}
export interface DividerBlock {
  type: 'divider';
}
export interface HtmlBlock {
  type: 'html';
  safe_html: string;
}
export interface EmbedBlock {
  type: 'embed';
  raw_html: string;
}
export type PageBlock =
  | HeadingBlock
  | ParagraphBlock
  | ImageBlock
  | ButtonBlock
  | DividerBlock
  | HtmlBlock
  | EmbedBlock;

export interface PublicPage {
  slug: string;
  title: string;
  blocks: PageBlock[];
  css: string;
  scope_id: string | number;
  published_at: string | null;
}

export interface SiteNavItem {
  slug: string;
  title: string;
}

// A not-published / missing page 404s — surfaced as null so the route can call
// notFound(); any other failure throws so the route can degrade gracefully.
export async function getPublicPage(slug: string): Promise<PublicPage | null> {
  const res = await fetch(
    `${apiBase()}/public/pages/${encodeURIComponent(slug)}`,
    { cache: 'no-store', headers: { accept: 'application/json' } },
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as PublicPage;
}

export async function getSiteNav(): Promise<SiteNavItem[]> {
  const res = await fetch(`${apiBase()}/public/site-nav`, {
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as SiteNavItem[];
}

// ---------------------------------------------------------------------------
// Forms / workflow engine — public (submitter-facing) surface. Only
// submitter-facing fields come back from the server; internal fields are
// excluded server-side. The server is the authority on validation — the
// client mirrors `required` / `show_if` for UX only.
// ---------------------------------------------------------------------------
export type FormFieldType =
  | 'text'
  | 'number'
  | 'date'
  | 'select'
  | 'multiselect'
  | 'boolean'
  | 'file';

// An option is either a bare value or a {value, label} pair.
export type FormFieldOption = string | { value: string; label: string };

export interface FormFieldValidation {
  required?: boolean;
  required_if?: { field: string; eq: unknown };
  regex?: string;
  min?: number;
  max?: number;
}

export interface FormFieldCondition {
  field: string;
  eq: unknown;
}

export interface FormField {
  key: string;
  type: FormFieldType;
  label: string;
  options?: FormFieldOption[];
  visibility: string;
  validation: FormFieldValidation;
  show_if?: FormFieldCondition;
}

export interface FormSchema {
  fields: FormField[];
}

export interface PublicForm {
  key: string;
  name: string;
  purpose: string;
  schema: FormSchema;
}

// A missing / unpublished form key 404s — surfaced as null so the route can
// call notFound(); any other failure throws so the route can degrade.
export async function getForm(key: string): Promise<PublicForm | null> {
  const res = await fetch(`${apiBase()}/forms/${encodeURIComponent(key)}`, {
    cache: 'no-store',
    headers: { accept: 'application/json' },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as PublicForm;
}

export async function submitForm(
  key: string,
  answers: Record<string, unknown>,
): Promise<{ id: number }> {
  const res = await fetch(
    `${apiBase()}/forms/${encodeURIComponent(key)}/submissions`,
    {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify({ answers }),
    },
  );
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as { id: number };
}
