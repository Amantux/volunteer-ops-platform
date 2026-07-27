// Authenticated client for the Volunteer Ops app surfaces.
// The opaque session token is the ONLY thing we persist (localStorage); no
// passwords or personal data are stored client-side.

import { ApiError, apiBase, parseError, type PageBlock } from '@/lib/api';

export { ApiError };
export type { PageBlock };

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

// Recurrence cadence for the slot builder. `none` produces a single slot.
export type ScheduleRepeat = 'none' | 'daily' | 'weekly' | 'biweekly';

// One role row in the slot builder, e.g. { name: 'Greeter', capacity: 4 }.
// `required_qualification_type_id`, when set, restricts the role to volunteers
// holding a current qualification of that type.
export interface ScheduleRole {
  name: string;
  capacity: number;
  required_qualification_type_id?: number;
  // When true, only volunteers with a current (cleared, unexpired) background
  // check may claim this role. Omitted/false leaves the role open.
  requires_background_check?: boolean;
}

// The recurring-slot builder payload. Times are ISO 8601; the server
// re-validates (end after start, at least one role, count 1..52).
export interface ScheduleInput {
  starts_at: string;
  ends_at: string;
  location: string;
  roles: ScheduleRole[];
  repeat: ScheduleRepeat;
  count: number;
}

export interface ScheduleResult {
  created: number;
  shift_ids: number[];
}

// Create a signup sheet (event). `is_public` sheets surface on the public
// Opportunities / Calendar pages.
export function createEvent(input: {
  title: string;
  description?: string;
  kind?: string;
  is_public?: boolean;
}): Promise<{ id: number }> {
  return authPost<{ id: number }>('/coordinator/events', input);
}

// Generate one or more time slots (shifts) for an event from the recurring
// builder. Returns how many were created and their ids.
export function createSchedule(
  eventId: number,
  input: ScheduleInput,
): Promise<ScheduleResult> {
  return authPost<ScheduleResult>(
    `/coordinator/events/${eventId}/schedule`,
    input,
  );
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

// Record a volunteer as a no-show for their claimed slot (terminal attendance
// state). Requires `shift.record_attendance`.
export function markNoShow(signupId: number): Promise<{ id: number }> {
  return authPost<{ id: number }>('/coordinator/no-show', {
    signup_id: signupId,
  });
}

// ---------------------------------------------------------------------------
// Qualifications — coordinator-managed eligibility gates (perm shift.manage).
// ---------------------------------------------------------------------------
export interface QualificationType {
  id: number;
  key: string;
  label: string;
  validity_days: number | null;
}

export function listQualificationTypes(): Promise<QualificationType[]> {
  return authGet<QualificationType[]>('/coordinator/qualification-types');
}

export function createQualificationType(input: {
  key: string;
  label: string;
  validity_days?: number;
}): Promise<{ id: number }> {
  return authPost<{ id: number }>('/coordinator/qualification-types', input);
}

// Grant a qualification type to a volunteer by email. The server returns a 400
// (surfaced via ApiError.message) if the email isn't a volunteer.
export function grantQualification(input: {
  volunteer_email: string;
  qualification_type_id: number;
}): Promise<{ id: number }> {
  return authPost<{ id: number }>('/coordinator/qualifications', input);
}

// ---------------------------------------------------------------------------
// Enrollments — long-term program placements (raiser/sitter etc). Distinct
// from per-shift signups: an enrollment is an ongoing relationship with a
// lifecycle. Read requires `enrollment.view`; write requires
// `enrollment.manage`.
// ---------------------------------------------------------------------------
export type EnrollmentStatus = 'active' | 'paused' | 'completed' | 'withdrawn';

export interface Enrollment {
  id: number;
  program_id: number;
  role: string;
  status: EnrollmentStatus;
  started_at: string | null;
  ended_at: string | null;
  notes: string | null;
  volunteer_name: string;
  volunteer_email: string;
}

export interface EnrollmentFilters {
  program_id?: number;
  role?: string;
  status?: EnrollmentStatus;
}

export function listEnrollments(
  filters: EnrollmentFilters = {},
): Promise<Enrollment[]> {
  const params = new URLSearchParams();
  if (filters.program_id != null) {
    params.set('program_id', String(filters.program_id));
  }
  if (filters.role) params.set('role', filters.role);
  if (filters.status) params.set('status', filters.status);
  const query = params.toString();
  return authGet<Enrollment[]>(
    `/coordinator/enrollments${query ? `?${query}` : ''}`,
  );
}

// Enrol a volunteer by email into a program role. The server returns a 400
// (surfaced via ApiError.message) if the email isn't a volunteer or the
// program is missing.
export function createEnrollment(input: {
  volunteer_email: string;
  program_id: number;
  role: string;
  notes?: string;
}): Promise<{ id: number }> {
  return authPost<{ id: number }>('/coordinator/enrollments', input);
}

export function setEnrollmentStatus(
  id: number,
  status: EnrollmentStatus,
): Promise<{ id: number }> {
  return authPost<{ id: number }>(`/coordinator/enrollments/${id}/status`, {
    status,
  });
}

// Background-check lifecycle. Internal/sensitive: gated on
// `volunteer.manage_background_check`. `expires_at` is an ISO datetime.
export type BackgroundCheckStatus =
  | 'none'
  | 'requested'
  | 'cleared'
  | 'expired';

export function setBackgroundCheck(input: {
  volunteer_email: string;
  status: BackgroundCheckStatus;
  expires_at?: string;
}): Promise<{ id: number }> {
  return authPost<{ id: number }>('/coordinator/background-check', input);
}

// ---------------------------------------------------------------------------
// Reporting — hours & impact (perm report.view_staffing).
// ---------------------------------------------------------------------------
export interface HoursByVolunteer {
  name: string;
  hours: number;
}

export interface HoursReport {
  total_hours: number;
  volunteers: number;
  by_volunteer: HoursByVolunteer[];
}

export function getHoursReport(): Promise<HoursReport> {
  return authGet<HoursReport>('/coordinator/reports/hours');
}

// ---------------------------------------------------------------------------
// CMS site builder (admin)
// ---------------------------------------------------------------------------
export interface AdminPage {
  id: number;
  slug: string;
  title: string;
  status: string;
  blocks: PageBlock[];
  custom_css: string;
  show_in_nav: boolean;
  nav_order: number;
  is_home: boolean;
  published_at: string | null;
  updated_at: string | null;
}

// Outgoing PATCH shape. `blocks` carries the editor's payload blocks — html /
// embed content is sent under key `html`; the server re-sanitizes and returns
// `safe_html` / `raw_html`. Typed loosely (unknown[]) for that asymmetry.
export interface PagePatch {
  title?: string;
  blocks?: unknown[];
  custom_css?: string;
  show_in_nav?: boolean;
  nav_order?: number;
}

export function listPages(): Promise<AdminPage[]> {
  return authGet<AdminPage[]>('/admin/pages');
}

export function getPage(id: number): Promise<AdminPage> {
  return authGet<AdminPage>(`/admin/pages/${id}`);
}

export function createPage(input: {
  slug: string;
  title: string;
}): Promise<{ id: number }> {
  return authPost<{ id: number }>('/admin/pages', input);
}

export async function updatePage(
  id: number,
  patch: PagePatch,
): Promise<AdminPage> {
  const res = await authFetch(`/admin/pages/${id}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(patch),
  });
  return (await res.json()) as AdminPage;
}

export function publishPage(id: number): Promise<AdminPage> {
  return authPost<AdminPage>(`/admin/pages/${id}/publish`);
}

export function unpublishPage(id: number): Promise<AdminPage> {
  return authPost<AdminPage>(`/admin/pages/${id}/unpublish`);
}

export function assistCopy(
  prompt: string,
): Promise<{ text: string; provider: string }> {
  return authPost<{ text: string; provider: string }>('/admin/pages/assist', {
    prompt,
  });
}

// ---------------------------------------------------------------------------
// Social media (admin) — human-approved publishing workflow.
// Lifecycle: draft → (submit) → pending_approval → (approve) → approved →
// (schedule / publish) → published. failed / partially_published can be
// re-published to retry the failed channels. Nothing here auto-publishes.
// ---------------------------------------------------------------------------
export type SocialPostStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'scheduled'
  | 'publishing'
  | 'published'
  | 'partially_published'
  | 'failed';

export interface SocialChannel {
  id: number;
  platform: string;
  handle: string;
  display_name: string;
  enabled: boolean;
  char_limit: number;
}

export interface SocialTarget {
  channel_id: number;
  status: string;
  external_ref: string | null;
  error: string | null;
}

export interface SocialPost {
  id: number;
  body: string;
  status: SocialPostStatus;
  source: string;
  scheduled_at: string | null;
  published_at: string | null;
  approved: boolean;
  draft_provider: string | null;
  targets: SocialTarget[];
}

export function listChannels(): Promise<SocialChannel[]> {
  return authGet<SocialChannel[]>('/social/channels');
}

export function createChannel(input: {
  platform?: string;
  handle: string;
  display_name?: string;
  char_limit?: number;
}): Promise<{ id: number }> {
  return authPost<{ id: number }>('/social/channels', {
    platform: 'manual',
    ...input,
  });
}

export function listPosts(): Promise<SocialPost[]> {
  return authGet<SocialPost[]>('/social/posts');
}

export function getPost(id: number): Promise<SocialPost> {
  return authGet<SocialPost>(`/social/posts/${id}`);
}

export function createPost(input: {
  body: string;
  channel_ids: number[];
  use_ai: boolean;
  prompt: string;
}): Promise<{ id: number }> {
  return authPost<{ id: number }>('/social/posts', input);
}

export async function updatePost(
  id: number,
  patch: { body?: string; channel_ids?: number[] },
): Promise<SocialPost> {
  const res = await authFetch(`/social/posts/${id}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(patch),
  });
  return (await res.json()) as SocialPost;
}

export function submitPost(id: number): Promise<SocialPost> {
  return authPost<SocialPost>(`/social/posts/${id}/submit`);
}

export function approvePost(id: number): Promise<SocialPost> {
  return authPost<SocialPost>(`/social/posts/${id}/approve`);
}

export function schedulePost(
  id: number,
  scheduledAt: string,
): Promise<SocialPost> {
  return authPost<SocialPost>(`/social/posts/${id}/schedule`, {
    scheduled_at: scheduledAt,
  });
}

export function publishPost(id: number): Promise<SocialPost> {
  return authPost<SocialPost>(`/social/posts/${id}/publish`);
}

// ---------------------------------------------------------------------------
// Forms / workflow engine (reviewer) — requires `forms.review`. A reviewer
// sees the full answer set (internal fields included) and drives the workflow
// instance through its allowed transitions.
// ---------------------------------------------------------------------------
export interface FormSubmission {
  id: number;
  status: string;
  answers: Record<string, unknown>;
  workflow_instance_id: number | null;
}

export interface WorkflowTransition {
  name: string;
  to: string;
  requires_approval: boolean;
}

export interface WorkflowInstance {
  id: number;
  current_state: string;
  status: string;
  deadline_at: string | null;
  allowed_transitions: WorkflowTransition[];
}

// A transition returns only the moved instance's head fields.
export interface TransitionResult {
  id: number;
  current_state: string;
  status: string;
}

export function listSubmissions(key: string): Promise<FormSubmission[]> {
  return authGet<FormSubmission[]>(
    `/submissions?key=${encodeURIComponent(key)}`,
  );
}

export function getSubmission(id: number): Promise<FormSubmission> {
  return authGet<FormSubmission>(`/submissions/${id}`);
}

export function getInstance(id: number): Promise<WorkflowInstance> {
  return authGet<WorkflowInstance>(`/instances/${id}`);
}

// Invoke a workflow transition. The Idempotency-Key makes a retry of the *same*
// intended action safe (the server dedupes on it); pass a value that is stable
// per (instance, transition), e.g. `${instanceId}:${name}`.
export async function runTransition(
  instanceId: number,
  name: string,
  note: string,
  idempotencyKey: string,
): Promise<TransitionResult> {
  const res = await authFetch(
    `/instances/${instanceId}/transitions/${encodeURIComponent(name)}`,
    {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({ note }),
    },
  );
  return (await res.json()) as TransitionResult;
}
