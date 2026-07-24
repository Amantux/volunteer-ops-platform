'use client';

import { useCallback, useEffect, useId, useState } from 'react';
import { formatWhen } from '@/lib/api';
import {
  ApiError,
  checkin,
  getBoard,
  getStaffing,
  logHours,
  type BoardEvent,
  type BoardSignup,
  type Staffing,
} from '@/lib/auth';

// A signup counts as "attended" once its status says so; only then do we hide
// the check-in / log-hours controls. (Status strings come from the backend.)
function isAttended(status: string): boolean {
  return status.trim().toLowerCase() === 'attended';
}

export default function CoordinatorPanel() {
  const [staffing, setStaffing] = useState<Staffing | null>(null);
  const [board, setBoard] = useState<BoardEvent[] | null>(null);
  const [loadError, setLoadError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setLoadError('');
    try {
      const [metrics, b] = await Promise.all([getStaffing(), getBoard()]);
      setStaffing(metrics);
      setBoard(b);
    } catch (err) {
      setLoadError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t load the roster. Please refresh in a moment.',
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function setRowError(id: number, message: string) {
    setRowErrors((prev) => ({ ...prev, [id]: message }));
  }
  function clearRowError(id: number) {
    setRowErrors((prev) => {
      if (!(id in prev)) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

  async function onCheckin(signupId: number) {
    clearRowError(signupId);
    setBusyId(signupId);
    try {
      await checkin(signupId);
      await load();
    } catch (err) {
      setRowError(
        signupId,
        err instanceof ApiError
          ? err.message
          : 'We couldn’t check this volunteer in. Please try again.',
      );
    } finally {
      setBusyId(null);
    }
  }

  async function onLogHours(signupId: number, hours: number) {
    clearRowError(signupId);
    setBusyId(signupId);
    try {
      await logHours(signupId, hours);
      await load();
    } catch (err) {
      setRowError(
        signupId,
        err instanceof ApiError
          ? err.message
          : 'We couldn’t log these hours. Please try again.',
      );
    } finally {
      setBusyId(null);
    }
  }

  // Derive the percentage from filled/capacity: unambiguous regardless of
  // whether the backend's fill_rate is a 0–1 fraction or already a percentage.
  const fillPct =
    staffing && staffing.capacity > 0
      ? Math.round((staffing.filled / staffing.capacity) * 100)
      : 0;

  return (
    <section aria-labelledby="coord-heading">
      <h2 id="coord-heading">Staffing</h2>

      {loadError && (
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load the roster</strong>
          <p>{loadError}</p>
        </div>
      )}

      {staffing && (
        <div className="panel">
          <div className="metric-grid">
            <div className="metric">
              <span className="metric-value">{fillPct}%</span>
              <span className="metric-label">Fill rate</span>
            </div>
            <div className="metric">
              <span className="metric-value">{staffing.filled}</span>
              <span className="metric-label">Roles filled</span>
            </div>
            <div className="metric">
              <span className="metric-value">{staffing.capacity}</span>
              <span className="metric-label">Total capacity</span>
            </div>
            <div className="metric">
              <span className="metric-value">{staffing.understaffed.length}</span>
              <span className="metric-label">Understaffed</span>
            </div>
          </div>

          {staffing.understaffed.length > 0 && (
            <div className="understaffed">
              <h3>Understaffed roles</h3>
              <ul className="plain-list">
                {staffing.understaffed.map((u) => (
                  <li key={`${u.role_id}-${u.shift_id}`}>
                    <span>{u.role}</span>
                    <span className="pill pill-waitlist">
                      {u.filled}/{u.capacity} filled
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <h2 id="board-heading" className="section-gap">
        Roster
      </h2>

      {board && board.length === 0 && (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            📋
          </div>
          <h3>No events on the board</h3>
          <p>There are no scheduled events to staff right now.</p>
        </div>
      )}

      {board &&
        board.map((event) => (
          <article className="panel event-card" key={event.event_id}>
            <div className="row-head">
              <h3>{event.title}</h3>
              <span className="muted">{event.kind}</span>
            </div>

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
                          <SignupRow
                            key={su.signup_id}
                            signup={su}
                            busy={busyId === su.signup_id}
                            error={rowErrors[su.signup_id]}
                            onCheckin={() => onCheckin(su.signup_id)}
                            onLogHours={(hours) =>
                              onLogHours(su.signup_id, hours)
                            }
                          />
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </article>
        ))}
    </section>
  );
}

function SignupRow({
  signup,
  busy,
  error,
  onCheckin,
  onLogHours,
}: {
  signup: BoardSignup;
  busy: boolean;
  error?: string;
  onCheckin: () => void;
  onLogHours: (hours: number) => void;
}) {
  const hoursId = useId();
  const [hours, setHours] = useState('');
  const [hoursError, setHoursError] = useState('');
  const attended = isAttended(signup.status);

  function submitHours(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setHoursError('');
    const value = Number(hours);
    if (!hours.trim() || Number.isNaN(value) || value <= 0) {
      setHoursError('Enter hours greater than 0.');
      return;
    }
    onLogHours(value);
  }

  return (
    <li className="signup-row">
      <div className="signup-main">
        <span className="signup-name">{signup.volunteer}</span>
        <span className="muted signup-status">{signup.status}</span>
      </div>

      {!attended && (
        <div className="signup-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onCheckin}
            disabled={busy}
          >
            {busy ? 'Working…' : 'Check in'}
          </button>

          <form className="hours-form" onSubmit={submitHours}>
            <label className="sr-only" htmlFor={hoursId}>
              Hours for {signup.volunteer}
            </label>
            <input
              id={hoursId}
              className="hours-input"
              type="number"
              inputMode="decimal"
              min="0"
              step="0.25"
              placeholder="Hours"
              value={hours}
              onChange={(e) => setHours(e.target.value)}
              aria-invalid={hoursError ? 'true' : undefined}
              aria-describedby={hoursError ? `${hoursId}-error` : undefined}
            />
            <button
              type="submit"
              className="btn btn-secondary btn-sm"
              disabled={busy}
            >
              {busy ? 'Saving…' : 'Log hours'}
            </button>
          </form>
        </div>
      )}

      {hoursError && (
        <p className="field-error" id={`${hoursId}-error`} role="alert">
          {hoursError}
        </p>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </li>
  );
}
