'use client';

import { useCallback, useEffect, useState } from 'react';
import { formatWhen } from '@/lib/api';
import {
  ApiError,
  cancelSignup,
  getEligible,
  getMyShifts,
  signup,
  type EligibleRole,
  type MyShift,
} from '@/lib/auth';

export default function VolunteerPanel() {
  const [shifts, setShifts] = useState<MyShift[] | null>(null);
  const [eligible, setEligible] = useState<EligibleRole[] | null>(null);
  const [loadError, setLoadError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  // Per-row action errors, keyed by role_id (signup) or signup_id (cancel).
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setLoadError('');
    try {
      const [mine, elig] = await Promise.all([getMyShifts(), getEligible()]);
      setShifts(mine);
      setEligible(elig);
    } catch (err) {
      setLoadError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t load your shifts. Please refresh in a moment.',
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

  async function onSignup(roleId: number) {
    clearRowError(roleId);
    setBusyId(roleId);
    try {
      await signup(roleId);
      await load();
    } catch (err) {
      setRowError(
        roleId,
        err instanceof ApiError
          ? err.message
          : 'We couldn’t sign you up. Please try again.',
      );
    } finally {
      setBusyId(null);
    }
  }

  async function onCancel(signupId: number) {
    clearRowError(signupId);
    setBusyId(signupId);
    try {
      await cancelSignup(signupId);
      await load();
    } catch (err) {
      setRowError(
        signupId,
        err instanceof ApiError
          ? err.message
          : 'We couldn’t cancel this shift. Please try again.',
      );
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section aria-labelledby="vol-heading">
      <h2 id="vol-heading">My shifts</h2>

      {loadError && (
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load your shifts</strong>
          <p>{loadError}</p>
        </div>
      )}

      {!loadError && shifts && shifts.length === 0 && (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            🗓️
          </div>
          <h3>No upcoming shifts yet</h3>
          <p>
            You haven’t signed up for any shifts. Browse the open roles below to
            get started.
          </p>
        </div>
      )}

      {shifts && shifts.length > 0 && (
        <ul className="card-list stack">
          {shifts.map((s) => (
            <li className="card panel" key={s.signup_id}>
              <div className="row-head">
                <h3>{s.event_title}</h3>
                {s.waitlisted && (
                  <span className="pill pill-waitlist">
                    Waitlisted
                    <span className="sr-only"> — you’ll be offered a place if one opens</span>
                  </span>
                )}
              </div>
              <dl className="detail-grid-inline">
                <div>
                  <dt>Role</dt>
                  <dd>{s.role}</dd>
                </div>
                <div>
                  <dt>When</dt>
                  <dd>{formatWhen(s.starts_at, s.ends_at)}</dd>
                </div>
                <div>
                  <dt>Location</dt>
                  <dd>{s.location || 'To be announced'}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{s.status}</dd>
                </div>
              </dl>
              {rowErrors[s.signup_id] && (
                <p className="field-error" role="alert">
                  {rowErrors[s.signup_id]}
                </p>
              )}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onCancel(s.signup_id)}
                disabled={busyId === s.signup_id}
              >
                {busyId === s.signup_id ? 'Cancelling…' : 'Cancel shift'}
              </button>
            </li>
          ))}
        </ul>
      )}

      <h2 id="eligible-heading" className="section-gap">
        Shifts you can join
      </h2>

      {!loadError && eligible && eligible.length === 0 && (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            ✅
          </div>
          <h3>Nothing open for you right now</h3>
          <p>
            There are no open roles matching your training at the moment. Check
            back soon — new shifts are added regularly.
          </p>
        </div>
      )}

      {eligible && eligible.length > 0 && (
        <ul className="card-list stack">
          {eligible.map((r) => (
            <li className="card panel" key={r.role_id}>
              <div className="row-head">
                <h3>{r.role}</h3>
                <span className="pill pill-open">
                  Open
                  <span className="sr-only"> — spaces available</span>
                </span>
              </div>
              <dl className="detail-grid-inline">
                <div>
                  <dt>When</dt>
                  <dd>{formatWhen(r.starts_at, null)}</dd>
                </div>
                <div>
                  <dt>Location</dt>
                  <dd>{r.location || 'To be announced'}</dd>
                </div>
                <div>
                  <dt>Why you’re eligible</dt>
                  <dd>{r.why_eligible}</dd>
                </div>
              </dl>
              {rowErrors[r.role_id] && (
                <p className="field-error" role="alert">
                  {rowErrors[r.role_id]}
                </p>
              )}
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => onSignup(r.role_id)}
                disabled={busyId === r.role_id}
              >
                {busyId === r.role_id ? 'Signing up…' : 'Sign up'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
