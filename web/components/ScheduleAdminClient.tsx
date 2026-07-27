'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useMemo, useState } from 'react';
import { formatWhen } from '@/lib/api';
import {
  ApiError,
  createEvent,
  createQualificationType,
  createSchedule,
  getBoard,
  getMe,
  getToken,
  grantQualification,
  listQualificationTypes,
  type BoardEvent,
  type Me,
  type QualificationType,
  type ScheduleRepeat,
  type ScheduleRole,
} from '@/lib/auth';

// The one permission this surface is gated on (mirrors the backend contract).
const P_MANAGE = 'shift.manage';

type State =
  | { kind: 'loading' }
  | {
      kind: 'ready';
      me: Me;
      board: BoardEvent[];
      qualTypes: QualificationType[];
    }
  | { kind: 'error'; message: string };

const REPEAT_OPTIONS: { value: ScheduleRepeat; label: string }[] = [
  { value: 'none', label: 'Does not repeat' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'biweekly', label: 'Every two weeks' },
];

const REPEAT_WORD: Record<ScheduleRepeat, string> = {
  none: 'one-off',
  daily: 'daily',
  weekly: 'weekly',
  biweekly: 'fortnightly',
};

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

// Combine a `<input type="date">` value and a `<input type="time">` value into
// an ISO 8601 timestamp. Returns '' if either part is missing/invalid.
function toIso(date: string, time: string): string {
  if (!date || !time) return '';
  const d = new Date(`${date}T${time}`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString();
}

export default function ScheduleAdminClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });

  // Locally created sheets that don't yet have slots won't appear on the board,
  // so we track them here to keep them selectable in the builder.
  const [localEvents, setLocalEvents] = useState<
    { event_id: number; title: string }[]
  >([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Page-level async feedback (aria-live).
  const [notice, setNotice] = useState('');
  const [actionError, setActionError] = useState('');

  const bounceOn401 = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        router.replace('/login');
        return true;
      }
      return false;
    },
    [router],
  );

  const load = useCallback(() => {
    if (!getToken()) {
      router.replace('/login');
      return;
    }
    setState({ kind: 'loading' });
    getMe()
      .then(async (me) => {
        // /board and /qualification-types also require shift.manage; skip the
        // calls when the permission is absent so we show the access note rather
        // than a 403.
        const canManage = me.permissions.includes(P_MANAGE);
        const [board, qualTypes] = canManage
          ? await Promise.all([getBoard(), listQualificationTypes()])
          : [[], []];
        setState({ kind: 'ready', me, board, qualTypes });
      })
      .catch((err: unknown) => {
        if (bounceOn401(err)) return;
        setState({
          kind: 'error',
          message: errText(
            err,
            'We couldn’t load the schedule. Please refresh in a moment.',
          ),
        });
      });
  }, [router, bounceOn401]);

  useEffect(() => {
    load();
  }, [load]);

  // Reload just the board (after creating slots) without dropping page state.
  const refreshBoard = useCallback(async () => {
    try {
      const board = await getBoard();
      setState((prev) =>
        prev.kind === 'ready' ? { ...prev, board } : prev,
      );
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(errText(err, 'We couldn’t refresh the board.'));
    }
  }, [bounceOn401]);

  // Reload just the qualification types (after creating one) so the role
  // selects and the grant form pick up the new option.
  const refreshQualTypes = useCallback(async () => {
    try {
      const qualTypes = await listQualificationTypes();
      setState((prev) => (prev.kind === 'ready' ? { ...prev, qualTypes } : prev));
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(errText(err, 'We couldn’t refresh qualification types.'));
    }
  }, [bounceOn401]);

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading the schedule…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Schedule</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load the schedule</strong>
          <p>{state.message}</p>
        </div>
      </div>
    );
  }

  const { me, board, qualTypes } = state;
  const canManage = me.permissions.includes(P_MANAGE);

  // Merge board events with locally-created (still slot-less) sheets. Board wins
  // on title if an id is present in both.
  const eventOptions = (() => {
    const map = new Map<number, string>();
    for (const l of localEvents) map.set(l.event_id, l.title);
    for (const e of board) map.set(e.event_id, e.title);
    return Array.from(map, ([event_id, title]) => ({ event_id, title }));
  })();

  const selectedEvent =
    selectedId != null
      ? board.find((e) => e.event_id === selectedId) ?? null
      : null;
  const selectedTitle =
    eventOptions.find((e) => e.event_id === selectedId)?.title ?? '';

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Schedule</h1>
          <p className="muted">
            Create signup sheets and generate the time slots volunteers claim
            from their dashboard’s “Shifts you can join.”
          </p>
        </div>
        <Link className="btn btn-secondary" href="/dashboard">
          Back to dashboard
        </Link>
      </div>

      {!canManage ? (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            🔒
          </div>
          <h2>Insufficient access</h2>
          <p>
            Managing signup sheets needs the “shift.manage” permission, which
            your account doesn’t have. Ask a coordinator to grant it.
          </p>
        </div>
      ) : (
        <>
          <div aria-live="polite">
            {notice && (
              <div className="alert alert-success" role="status">
                <p>{notice}</p>
              </div>
            )}
          </div>
          <div aria-live="assertive">
            {actionError && (
              <div className="alert alert-danger" role="alert">
                <strong>That didn’t work</strong>
                <p>{actionError}</p>
              </div>
            )}
          </div>

          <CreateSheet
            onCreated={(id, title) => {
              setActionError('');
              setNotice(`Sheet “${title}” created. Add slots to it below.`);
              setLocalEvents((prev) => [...prev, { event_id: id, title }]);
              setSelectedId(id);
            }}
            onAuthLost={() => router.replace('/login')}
          />

          <section className="section-gap" aria-labelledby="slots-heading">
            <h2 id="slots-heading">Add slots</h2>
            {eventOptions.length === 0 ? (
              <div className="empty">
                <div className="empty-icon" aria-hidden="true">
                  🗓️
                </div>
                <h3>No signup sheets yet</h3>
                <p>Create a sheet above, then generate its time slots here.</p>
              </div>
            ) : (
              <SlotBuilder
                events={eventOptions}
                qualTypes={qualTypes}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onCreated={async (count) => {
                  setActionError('');
                  setNotice(
                    `Created ${count} slot${count === 1 ? '' : 's'}.`,
                  );
                  await refreshBoard();
                }}
                onError={(msg) => {
                  setNotice('');
                  setActionError(msg);
                }}
                onAuthLost={() => router.replace('/login')}
              />
            )}
          </section>

          {selectedId != null && (
            <SheetView title={selectedTitle} event={selectedEvent} />
          )}

          <QualificationsPanel
            qualTypes={qualTypes}
            onChanged={refreshQualTypes}
            onAuthLost={() => router.replace('/login')}
          />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create a signup sheet (event).
// ---------------------------------------------------------------------------
function CreateSheet({
  onCreated,
  onAuthLost,
}: {
  onCreated: (id: number, title: string) => void;
  onAuthLost: () => void;
}) {
  const titleId = useId();
  const descId = useId();
  const publicId = useId();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [fieldError, setFieldError] = useState('');
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFieldError('');
    const t = title.trim();
    if (!t) {
      setFieldError('A sheet title is required.');
      return;
    }
    setBusy(true);
    try {
      const { id } = await createEvent({
        title: t,
        description: description.trim() || undefined,
        is_public: isPublic,
      });
      onCreated(id, t);
      setTitle('');
      setDescription('');
      setIsPublic(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setFieldError(
        errText(err, 'We couldn’t create that sheet. Please try again.'),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="create-sheet-heading">
      <h2 id="create-sheet-heading">Create a signup sheet</h2>

      <form onSubmit={onSubmit} noValidate>
        <div className="field">
          <label htmlFor={titleId}>
            Sheet title <span className="req">*</span>
          </label>
          <input
            id={titleId}
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-required="true"
            aria-invalid={fieldError ? 'true' : undefined}
            aria-describedby={fieldError ? `${titleId}-error` : undefined}
          />
          {fieldError && (
            <p className="field-error" id={`${titleId}-error`} role="alert">
              {fieldError}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor={descId}>Description</label>
          <textarea
            id={descId}
            className="cms-textarea"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="field">
          <label className="cms-check" htmlFor={publicId}>
            <input
              id={publicId}
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Public sheet — show on the site’s Opportunities and Calendar
          </label>
        </div>

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Creating…' : 'Create sheet'}
        </button>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Slot builder — the SignUp.com replacement. Tunable recurrence + roles.
// ---------------------------------------------------------------------------
interface RoleRow {
  key: number;
  name: string;
  capacity: string;
  // '' = no qualification required; otherwise the qualification type id.
  qualId: string;
  // When true, the role requires a current background check.
  bgCheck: boolean;
}

let roleKeySeq = 0;
function newRole(): RoleRow {
  roleKeySeq += 1;
  return { key: roleKeySeq, name: '', capacity: '1', qualId: '', bgCheck: false };
}

function SlotBuilder({
  events,
  qualTypes,
  selectedId,
  onSelect,
  onCreated,
  onError,
  onAuthLost,
}: {
  events: { event_id: number; title: string }[];
  qualTypes: QualificationType[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onCreated: (count: number) => void | Promise<void>;
  onError: (message: string) => void;
  onAuthLost: () => void;
}) {
  const eventId = useId();
  const dateId = useId();
  const startId = useId();
  const endId = useId();
  const locationId = useId();
  const repeatId = useId();
  const countId = useId();

  const [date, setDate] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [location, setLocation] = useState('');
  const [repeat, setRepeat] = useState<ScheduleRepeat>('none');
  const [count, setCount] = useState('1');
  const [roles, setRoles] = useState<RoleRow[]>(() => [newRole()]);

  const [fieldError, setFieldError] = useState('');
  const [busy, setBusy] = useState(false);

  const occurrences = repeat === 'none' ? 1 : Math.max(1, Number(count) || 1);

  // Live preview, e.g. "4 weekly slots · Tue 10:00–12:00 · 2 roles".
  const preview = useMemo(() => {
    const startsAt = toIso(date, startTime);
    const endsAt = toIso(date, endTime);
    if (!startsAt) return '';
    const filledRoles = roles.filter((r) => r.name.trim()).length;
    const roleLabel =
      filledRoles === 1 ? '1 role' : `${filledRoles} roles`;
    const when = formatWhen(startsAt, endsAt || null);
    const slots =
      repeat === 'none'
        ? '1 one-off slot'
        : `${occurrences} ${REPEAT_WORD[repeat]} slots`;
    return `${slots} · ${when} · ${roleLabel}`;
  }, [date, startTime, endTime, repeat, occurrences, roles]);

  function updateRole(key: number, patch: Partial<RoleRow>) {
    setRoles((prev) =>
      prev.map((r) => (r.key === key ? { ...r, ...patch } : r)),
    );
  }
  function addRole() {
    setRoles((prev) => [...prev, newRole()]);
  }
  function removeRole(key: number) {
    setRoles((prev) =>
      prev.length > 1 ? prev.filter((r) => r.key !== key) : prev,
    );
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFieldError('');

    if (selectedId == null) {
      setFieldError('Choose a signup sheet first.');
      return;
    }
    const startsAt = toIso(date, startTime);
    const endsAt = toIso(date, endTime);
    if (!startsAt) {
      setFieldError('A date and start time are required.');
      return;
    }
    if (!endsAt) {
      setFieldError('An end time is required.');
      return;
    }
    if (endsAt <= startsAt) {
      setFieldError('The end time must be after the start time.');
      return;
    }
    if (!location.trim()) {
      setFieldError('A location is required.');
      return;
    }
    const n = Number(count);
    if (repeat !== 'none' && (!Number.isInteger(n) || n < 1 || n > 52)) {
      setFieldError('Enter how many times it repeats (1–52).');
      return;
    }
    const cleanedRoles: ScheduleRole[] = [];
    for (const r of roles) {
      const name = r.name.trim();
      const cap = Number(r.capacity);
      if (!name) continue;
      if (!Number.isInteger(cap) || cap < 1) {
        setFieldError(`Give “${name}” a capacity of at least 1.`);
        return;
      }
      const role: ScheduleRole = { name, capacity: cap };
      if (r.qualId) role.required_qualification_type_id = Number(r.qualId);
      if (r.bgCheck) role.requires_background_check = true;
      cleanedRoles.push(role);
    }
    if (cleanedRoles.length === 0) {
      setFieldError('Add at least one role with a name and capacity.');
      return;
    }

    setBusy(true);
    try {
      const result = await createSchedule(selectedId, {
        starts_at: startsAt,
        ends_at: endsAt,
        location: location.trim(),
        roles: cleanedRoles,
        repeat,
        count: occurrences,
      });
      await onCreated(result.created);
      // Reset the time-specific inputs; keep roles/location for the next batch.
      setDate('');
      setStartTime('');
      setEndTime('');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      onError(
        errText(err, 'We couldn’t create those slots. Please try again.'),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={onSubmit} noValidate>
      <div className="field">
        <label htmlFor={eventId}>
          Signup sheet <span className="req">*</span>
        </label>
        <select
          id={eventId}
          className="cms-select"
          value={selectedId ?? ''}
          onChange={(e) => onSelect(Number(e.target.value))}
          required
        >
          <option value="" disabled>
            Choose a sheet…
          </option>
          {events.map((ev) => (
            <option key={ev.event_id} value={ev.event_id}>
              {ev.title}
            </option>
          ))}
        </select>
      </div>

      <div className="cms-field-row">
        <div className="field cms-grow">
          <label htmlFor={dateId}>
            Date <span className="req">*</span>
          </label>
          <input
            id={dateId}
            type="date"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div className="field cms-grow">
          <label htmlFor={startId}>
            Start time <span className="req">*</span>
          </label>
          <input
            id={startId}
            type="time"
            required
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
          />
        </div>
        <div className="field cms-grow">
          <label htmlFor={endId}>
            End time <span className="req">*</span>
          </label>
          <input
            id={endId}
            type="time"
            required
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor={locationId}>
          Location <span className="req">*</span>
        </label>
        <input
          id={locationId}
          type="text"
          required
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
      </div>

      <div className="cms-field-row">
        <div className="field cms-grow">
          <label htmlFor={repeatId}>Repeat</label>
          <select
            id={repeatId}
            className="cms-select"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value as ScheduleRepeat)}
          >
            {REPEAT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field cms-level">
          <label htmlFor={countId}>Occurrences</label>
          <input
            id={countId}
            type="number"
            min="1"
            max="52"
            step="1"
            value={count}
            onChange={(e) => setCount(e.target.value)}
            disabled={repeat === 'none'}
          />
        </div>
      </div>

      <fieldset className="schedule-roles">
        <legend>
          Roles <span className="req">*</span>
        </legend>
        <p className="muted" style={{ marginTop: 0 }}>
          Each role can be claimed up to its capacity (e.g. Greeter ×4).
        </p>
        <ul className="plain-list">
          {roles.map((r, i) => (
            <li className="cms-field-row" key={r.key}>
              <div className="field cms-grow">
                <label className="sr-only" htmlFor={`${eventId}-role-${r.key}`}>
                  Role {i + 1} name
                </label>
                <input
                  id={`${eventId}-role-${r.key}`}
                  type="text"
                  placeholder="Role name (e.g. Greeter)"
                  value={r.name}
                  onChange={(e) => updateRole(r.key, { name: e.target.value })}
                />
              </div>
              <div className="field cms-level">
                <label
                  className="sr-only"
                  htmlFor={`${eventId}-cap-${r.key}`}
                >
                  Role {i + 1} capacity
                </label>
                <input
                  id={`${eventId}-cap-${r.key}`}
                  type="number"
                  min="1"
                  step="1"
                  aria-label={`Capacity for role ${i + 1}`}
                  value={r.capacity}
                  onChange={(e) =>
                    updateRole(r.key, { capacity: e.target.value })
                  }
                />
              </div>
              <div className="field cms-grow">
                <label className="sr-only" htmlFor={`${eventId}-qual-${r.key}`}>
                  Required qualification for role {i + 1}
                </label>
                <select
                  id={`${eventId}-qual-${r.key}`}
                  className="cms-select"
                  value={r.qualId}
                  onChange={(e) => updateRole(r.key, { qualId: e.target.value })}
                >
                  <option value="">None — anyone eligible</option>
                  {qualTypes.map((q) => (
                    <option key={q.id} value={q.id}>
                      Requires {q.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field cms-level">
                <label className="cms-check" htmlFor={`${eventId}-bg-${r.key}`}>
                  <input
                    id={`${eventId}-bg-${r.key}`}
                    type="checkbox"
                    checked={r.bgCheck}
                    onChange={(e) =>
                      updateRole(r.key, { bgCheck: e.target.checked })
                    }
                  />
                  Requires background check
                </label>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => removeRole(r.key)}
                disabled={roles.length === 1}
                aria-label={`Remove role ${i + 1}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={addRole}
        >
          Add role
        </button>
      </fieldset>

      {preview && (
        <p className="muted schedule-preview" aria-live="polite">
          {preview}
        </p>
      )}

      {fieldError && (
        <p className="field-error" role="alert">
          {fieldError}
        </p>
      )}

      <button
        type="submit"
        className="btn btn-primary section-gap"
        disabled={busy}
      >
        {busy ? 'Adding…' : 'Add slots'}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Sheet view — the selected event's generated slots, read from the board.
// ---------------------------------------------------------------------------
function SheetView({
  title,
  event,
}: {
  title: string;
  event: BoardEvent | null;
}) {
  return (
    <section className="section-gap" aria-labelledby="sheet-heading">
      <h2 id="sheet-heading">Slots on “{title}”</h2>

      {!event || event.shifts.length === 0 ? (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            📋
          </div>
          <h3>No slots yet</h3>
          <p>Use “Add slots” above to generate this sheet’s time slots.</p>
        </div>
      ) : (
        <>
          <article className="panel event-card">
            {event.shifts.map((shift) => (
              <div className="shift-block" key={shift.shift_id}>
                <p className="shift-when">
                  {formatWhen(shift.starts_at, shift.ends_at)}
                  {' · '}
                  {shift.location || 'To be announced'}
                  {shift.is_open && (
                    <span className="pill pill-open pill-inline">Open</span>
                  )}
                </p>

                {shift.roles.map((role) => (
                  <div className="role-block" key={role.role_id}>
                    <div className="row-head">
                      <h4>{role.role}</h4>
                      <span
                        className={
                          role.filled >= role.capacity
                            ? 'pill pill-open'
                            : 'pill pill-waitlist'
                        }
                      >
                        {role.filled}/{role.capacity} filled
                      </span>
                    </div>

                    {role.signups.length === 0 ? (
                      <p className="muted no-signups">No sign-ups yet.</p>
                    ) : (
                      <ul className="plain-list">
                        {role.signups.map((su) => (
                          <li className="signup-row" key={su.signup_id}>
                            <div className="signup-main">
                              <span className="signup-name">
                                {su.volunteer}
                              </span>
                              <span className="muted signup-status">
                                {su.status}
                              </span>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </article>
          <p className="muted section-gap">
            Check volunteers in and log hours from the{' '}
            <Link href="/dashboard">dashboard</Link>.
          </p>
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Qualifications — collapsible coordinator tool: define qualification types and
// grant them to volunteers by email. Roles above can then require a type.
// ---------------------------------------------------------------------------
function QualificationsPanel({
  qualTypes,
  onChanged,
  onAuthLost,
}: {
  qualTypes: QualificationType[];
  onChanged: () => void | Promise<void>;
  onAuthLost: () => void;
}) {
  return (
    <details className="faq-item section-gap">
      <summary>Qualifications</summary>
      <div className="faq-answer">
        <p className="muted" style={{ marginTop: 0 }}>
          Define qualification types (e.g. Food Handling, First Aid) and grant
          them to volunteers. A slot role can then require a type so only
          qualified volunteers see it.
        </p>

        {qualTypes.length > 0 && (
          <ul className="plain-list section-gap">
            {qualTypes.map((q) => (
              <li key={q.id}>
                <span className="signup-name">{q.label}</span>
                <span className="muted">{q.key}</span>
              </li>
            ))}
          </ul>
        )}

        <CreateQualType onCreated={onChanged} onAuthLost={onAuthLost} />
        <GrantQual qualTypes={qualTypes} onAuthLost={onAuthLost} />
      </div>
    </details>
  );
}

function CreateQualType({
  onCreated,
  onAuthLost,
}: {
  onCreated: () => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const keyId = useId();
  const labelId = useId();
  const [key, setKey] = useState('');
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setNotice('');
    const k = key.trim();
    const l = label.trim();
    if (!k || !l) {
      setError('A key and a label are both required.');
      return;
    }
    setBusy(true);
    try {
      await createQualificationType({ key: k, label: l });
      setNotice(`Qualification type “${l}” created.`);
      setKey('');
      setLabel('');
      await onCreated();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setError(
        errText(err, 'We couldn’t create that qualification type. Try again.'),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="section-gap" onSubmit={onSubmit} noValidate>
      <h3>Add a qualification type</h3>
      <div className="cms-field-row">
        <div className="field cms-grow">
          <label htmlFor={keyId}>
            Key <span className="req">*</span>
          </label>
          <input
            id={keyId}
            type="text"
            placeholder="e.g. food_handling"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
        </div>
        <div className="field cms-grow">
          <label htmlFor={labelId}>
            Label <span className="req">*</span>
          </label>
          <input
            id={labelId}
            type="text"
            placeholder="e.g. Food Handling"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
      </div>
      <div aria-live="polite">
        {notice && (
          <p className="field-success" role="status">
            {notice}
          </p>
        )}
      </div>
      <div aria-live="assertive">
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <button type="submit" className="btn btn-secondary" disabled={busy}>
        {busy ? 'Adding…' : 'Add type'}
      </button>
    </form>
  );
}

function GrantQual({
  qualTypes,
  onAuthLost,
}: {
  qualTypes: QualificationType[];
  onAuthLost: () => void;
}) {
  const emailId = useId();
  const typeId = useId();
  const [email, setEmail] = useState('');
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setNotice('');
    const addr = email.trim();
    if (!addr) {
      setError('A volunteer email is required.');
      return;
    }
    if (!selected) {
      setError('Choose a qualification type to grant.');
      return;
    }
    setBusy(true);
    try {
      await grantQualification({
        volunteer_email: addr,
        qualification_type_id: Number(selected),
      });
      setNotice(`Granted to ${addr}.`);
      setEmail('');
      setSelected('');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      // Surfaces the backend's 400 detail (e.g. the email isn't a volunteer).
      setError(errText(err, 'We couldn’t grant that qualification. Try again.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="section-gap" onSubmit={onSubmit} noValidate>
      <h3>Grant a qualification</h3>
      {qualTypes.length === 0 ? (
        <p className="muted">Add a qualification type first, then grant it.</p>
      ) : (
        <>
          <div className="cms-field-row">
            <div className="field cms-grow">
              <label htmlFor={emailId}>
                Volunteer email <span className="req">*</span>
              </label>
              <input
                id={emailId}
                type="email"
                placeholder="volunteer@example.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="field cms-grow">
              <label htmlFor={typeId}>
                Qualification <span className="req">*</span>
              </label>
              <select
                id={typeId}
                className="cms-select"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="" disabled>
                  Choose a type…
                </option>
                {qualTypes.map((q) => (
                  <option key={q.id} value={q.id}>
                    {q.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div aria-live="polite">
            {notice && (
              <p className="field-success" role="status">
                {notice}
              </p>
            )}
          </div>
          <div aria-live="assertive">
            {error && (
              <p className="field-error" role="alert">
                {error}
              </p>
            )}
          </div>
          <button type="submit" className="btn btn-secondary" disabled={busy}>
            {busy ? 'Granting…' : 'Grant qualification'}
          </button>
        </>
      )}
    </form>
  );
}
