'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useMemo, useState } from 'react';
import { formatWhen } from '@/lib/api';
import {
  ApiError,
  createEnrollment,
  getMe,
  getToken,
  listEnrollments,
  setBackgroundCheck,
  setEnrollmentStatus,
  type BackgroundCheckStatus,
  type Enrollment,
  type EnrollmentFilters,
  type EnrollmentStatus,
  type Me,
} from '@/lib/auth';

// Permissions this surface is gated on (mirror the backend contract).
const P_VIEW = 'enrollment.view';
const P_MANAGE = 'enrollment.manage';
const P_BG = 'volunteer.manage_background_check';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me; enrollments: Enrollment[] }
  | { kind: 'no-access'; me: Me }
  | { kind: 'error'; message: string };

const STATUS_OPTIONS: { value: EnrollmentStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
  { value: 'withdrawn', label: 'Withdrawn' },
];

// Which pill each status wears — meaning is carried by the label text, not
// colour alone (WCAG 1.4.1).
const STATUS_PILL: Record<EnrollmentStatus, string> = {
  active: 'pill pill-open',
  paused: 'pill pill-waitlist',
  completed: 'pill pill-neutral',
  withdrawn: 'pill pill-danger',
};

// The transitions offered per current status. Terminal states offer none.
const STATUS_ACTIONS: Record<
  EnrollmentStatus,
  { label: string; to: EnrollmentStatus }[]
> = {
  active: [
    { label: 'Pause', to: 'paused' },
    { label: 'Complete', to: 'completed' },
    { label: 'Withdraw', to: 'withdrawn' },
  ],
  paused: [
    { label: 'Resume', to: 'active' },
    { label: 'Complete', to: 'completed' },
    { label: 'Withdraw', to: 'withdrawn' },
  ],
  completed: [],
  withdrawn: [],
};

const BG_OPTIONS: { value: BackgroundCheckStatus; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'requested', label: 'Requested' },
  { value: 'cleared', label: 'Cleared' },
  { value: 'expired', label: 'Expired' },
];

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

function statusLabel(status: EnrollmentStatus): string {
  return STATUS_OPTIONS.find((s) => s.value === status)?.label ?? status;
}

export default function EnrollmentsClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [filters, setFilters] = useState<EnrollmentFilters>({});

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

  const load = useCallback(
    (nextFilters: EnrollmentFilters) => {
      if (!getToken()) {
        router.replace('/login');
        return;
      }
      setState({ kind: 'loading' });
      getMe()
        .then(async (me) => {
          if (!me.permissions.includes(P_VIEW)) {
            setState({ kind: 'no-access', me });
            return;
          }
          const enrollments = await listEnrollments(nextFilters);
          setState({ kind: 'ready', me, enrollments });
        })
        .catch((err: unknown) => {
          if (bounceOn401(err)) return;
          setState({
            kind: 'error',
            message: errText(
              err,
              'We couldn’t load enrollments. Please refresh in a moment.',
            ),
          });
        });
    },
    [router, bounceOn401],
  );

  useEffect(() => {
    load(filters);
    // Re-run only when the applied filters change.
  }, [load, filters]);

  // Reload the table (after a mutation) without dropping page state.
  const refresh = useCallback(async () => {
    try {
      const enrollments = await listEnrollments(filters);
      setState((prev) =>
        prev.kind === 'ready' ? { ...prev, enrollments } : prev,
      );
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(errText(err, 'We couldn’t refresh enrollments.'));
    }
  }, [filters, bounceOn401]);

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading enrollments…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Enrollments</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load enrollments</strong>
          <p>{state.message}</p>
        </div>
      </div>
    );
  }

  if (state.kind === 'no-access') {
    return (
      <div className="container page">
        <div className="page-head">
          <div>
            <h1>Enrollments</h1>
          </div>
          <Link className="btn btn-secondary" href="/dashboard">
            Back to dashboard
          </Link>
        </div>
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            🔒
          </div>
          <h2>Insufficient access</h2>
          <p>
            Viewing enrollments needs the “enrollment.view” permission, which
            your account doesn’t have. Ask a coordinator to grant it.
          </p>
        </div>
      </div>
    );
  }

  const { me, enrollments } = state;
  const canManage = me.permissions.includes(P_MANAGE);
  const canBg = me.permissions.includes(P_BG);

  async function onStatus(id: number, to: EnrollmentStatus) {
    setNotice('');
    setActionError('');
    try {
      await setEnrollmentStatus(id, to);
      setNotice(`Enrollment marked ${statusLabel(to).toLowerCase()}.`);
      await refresh();
    } catch (err) {
      if (bounceOn401(err)) return;
      setActionError(
        errText(err, 'We couldn’t update that enrollment. Please try again.'),
      );
    }
  }

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Enrollments</h1>
          <p className="muted">
            Long-term program placements and their lifecycle — distinct from
            per-shift signups.
          </p>
        </div>
        <Link className="btn btn-secondary" href="/dashboard">
          Back to dashboard
        </Link>
      </div>

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

      <FilterBar filters={filters} onApply={setFilters} />

      <section className="section-gap" aria-labelledby="enrollments-heading">
        <h2 id="enrollments-heading">Enrollments</h2>
        {enrollments.length === 0 ? (
          <div className="empty">
            <div className="empty-icon" aria-hidden="true">
              🧭
            </div>
            <h3>No enrollments match</h3>
            <p>
              Adjust the filters above, or enrol a volunteer using the form
              below.
            </p>
          </div>
        ) : (
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col">Volunteer</th>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col">Started</th>
                <th scope="col">Ended</th>
                {canManage && <th scope="col">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {enrollments.map((en) => (
                <tr key={en.id}>
                  <td>{en.volunteer_name}</td>
                  <td>{en.volunteer_email}</td>
                  <td>{en.role}</td>
                  <td>
                    <span className={STATUS_PILL[en.status]}>
                      {statusLabel(en.status)}
                    </span>
                  </td>
                  <td>
                    {en.started_at ? formatWhen(en.started_at, null) : '—'}
                  </td>
                  <td>{en.ended_at ? formatWhen(en.ended_at, null) : '—'}</td>
                  {canManage && (
                    <td>
                      <div className="cms-actions">
                        {STATUS_ACTIONS[en.status].length === 0 ? (
                          <span className="muted">No actions</span>
                        ) : (
                          STATUS_ACTIONS[en.status].map((a) => (
                            <button
                              key={a.to}
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => onStatus(en.id, a.to)}
                            >
                              {a.label}
                            </button>
                          ))
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {canManage && (
        <EnrolForm
          onEnrolled={async () => {
            await refresh();
          }}
          onAuthLost={() => router.replace('/login')}
        />
      )}

      {canBg && (
        <BackgroundCheckForm onAuthLost={() => router.replace('/login')} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter bar — program_id / role / status via a small form that applies on
// submit (so screen-reader users aren't interrupted mid-typing).
// ---------------------------------------------------------------------------
function FilterBar({
  filters,
  onApply,
}: {
  filters: EnrollmentFilters;
  onApply: (next: EnrollmentFilters) => void;
}) {
  const programId = useId();
  const roleId = useId();
  const statusId = useId();

  const [program, setProgram] = useState(
    filters.program_id != null ? String(filters.program_id) : '',
  );
  const [role, setRole] = useState(filters.role ?? '');
  const [status, setStatus] = useState<EnrollmentStatus | ''>(
    filters.status ?? '',
  );

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const next: EnrollmentFilters = {};
    const p = Number(program);
    if (program.trim() && Number.isInteger(p) && p > 0) next.program_id = p;
    if (role.trim()) next.role = role.trim();
    if (status) next.status = status;
    onApply(next);
  }

  function onClear() {
    setProgram('');
    setRole('');
    setStatus('');
    onApply({});
  }

  return (
    <form className="panel" onSubmit={onSubmit} aria-labelledby="filters-head">
      <h2 id="filters-head">Filter</h2>
      <div className="cms-field-row">
        <div className="field cms-level">
          <label htmlFor={programId}>Program ID</label>
          <input
            id={programId}
            type="number"
            min="1"
            step="1"
            inputMode="numeric"
            value={program}
            onChange={(e) => setProgram(e.target.value)}
          />
        </div>
        <div className="field cms-grow">
          <label htmlFor={roleId}>Role</label>
          <input
            id={roleId}
            type="text"
            placeholder="e.g. raiser"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          />
        </div>
        <div className="field cms-grow">
          <label htmlFor={statusId}>Status</label>
          <select
            id={statusId}
            className="cms-select"
            value={status}
            onChange={(e) =>
              setStatus(e.target.value as EnrollmentStatus | '')
            }
          >
            <option value="">Any status</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="cms-actions">
        <button type="submit" className="btn btn-secondary">
          Apply filters
        </button>
        <button type="button" className="btn btn-secondary" onClick={onClear}>
          Clear
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Enrol a volunteer into a program role.
// ---------------------------------------------------------------------------
function EnrolForm({
  onEnrolled,
  onAuthLost,
}: {
  onEnrolled: () => void | Promise<void>;
  onAuthLost: () => void;
}) {
  const emailId = useId();
  const programId = useId();
  const roleId = useId();
  const notesId = useId();

  const [email, setEmail] = useState('');
  const [program, setProgram] = useState('');
  const [role, setRole] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setNotice('');
    const addr = email.trim();
    const r = role.trim();
    const p = Number(program);
    if (!addr) {
      setError('A volunteer email is required.');
      return;
    }
    if (!program.trim() || !Number.isInteger(p) || p < 1) {
      setError('A numeric Program ID is required.');
      return;
    }
    if (!r) {
      setError('A role is required.');
      return;
    }
    setBusy(true);
    try {
      await createEnrollment({
        volunteer_email: addr,
        program_id: p,
        role: r,
        notes: notes.trim() || undefined,
      });
      setNotice(`Enrolled ${addr} as ${r}.`);
      setEmail('');
      setProgram('');
      setRole('');
      setNotes('');
      await onEnrolled();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      // Surfaces the backend's 400 detail (e.g. not a volunteer / no program).
      setError(errText(err, 'We couldn’t enrol that volunteer. Try again.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel section-gap" aria-labelledby="enrol-heading">
      <h2 id="enrol-heading">Enrol a volunteer</h2>
      <form onSubmit={onSubmit} noValidate>
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
          <div className="field cms-level">
            <label htmlFor={programId}>
              Program ID <span className="req">*</span>
            </label>
            <input
              id={programId}
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              value={program}
              onChange={(e) => setProgram(e.target.value)}
            />
          </div>
          <div className="field cms-grow">
            <label htmlFor={roleId}>
              Role <span className="req">*</span>
            </label>
            <input
              id={roleId}
              type="text"
              placeholder="e.g. raiser"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor={notesId}>Notes</label>
          <textarea
            id={notesId}
            className="cms-textarea"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
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
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Enrolling…' : 'Enrol volunteer'}
        </button>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Background check — internal/sensitive. Records the check lifecycle for a
// volunteer. Gated on `volunteer.manage_background_check`.
// ---------------------------------------------------------------------------
function BackgroundCheckForm({ onAuthLost }: { onAuthLost: () => void }) {
  const emailId = useId();
  const statusId = useId();
  const expiryId = useId();

  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<BackgroundCheckStatus>('requested');
  const [expiry, setExpiry] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Only a cleared check carries an expiry date; hide the field otherwise.
  const showExpiry = useMemo(() => status === 'cleared', [status]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setNotice('');
    const addr = email.trim();
    if (!addr) {
      setError('A volunteer email is required.');
      return;
    }
    let expiresAt: string | undefined;
    if (showExpiry && expiry) {
      const d = new Date(expiry);
      if (Number.isNaN(d.getTime())) {
        setError('Enter a valid expiry date.');
        return;
      }
      expiresAt = d.toISOString();
    }
    setBusy(true);
    try {
      await setBackgroundCheck({
        volunteer_email: addr,
        status,
        expires_at: expiresAt,
      });
      setNotice(`Background check for ${addr} set to ${status}.`);
      setEmail('');
      setExpiry('');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthLost();
        return;
      }
      setError(errText(err, 'We couldn’t record that check. Try again.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel section-gap" aria-labelledby="bg-heading">
      <h2 id="bg-heading">Background check</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Internal and sensitive. Records a volunteer’s background-check status;
        roles that require a check only admit volunteers whose check is current.
      </p>
      <form onSubmit={onSubmit} noValidate>
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
            <label htmlFor={statusId}>
              Status <span className="req">*</span>
            </label>
            <select
              id={statusId}
              className="cms-select"
              value={status}
              onChange={(e) =>
                setStatus(e.target.value as BackgroundCheckStatus)
              }
            >
              {BG_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          {showExpiry && (
            <div className="field cms-grow">
              <label htmlFor={expiryId}>Expires</label>
              <input
                id={expiryId}
                type="date"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
              />
            </div>
          )}
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
          {busy ? 'Saving…' : 'Record check'}
        </button>
      </form>
    </section>
  );
}
