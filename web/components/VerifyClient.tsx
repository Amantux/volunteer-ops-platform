'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { ApiError, verifyToken, type RegisterResult } from '@/lib/api';

type State =
  | { kind: 'missing' }
  | { kind: 'verifying' }
  | { kind: 'done'; result: RegisterResult }
  | { kind: 'error'; message: string };

export default function VerifyClient() {
  const params = useSearchParams();
  const token = params.get('token');
  const [state, setState] = useState<State>(
    token ? { kind: 'verifying' } : { kind: 'missing' },
  );
  // Guard against duplicate POSTs (React strict mode double-invokes effects).
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;
    let active = true;
    verifyToken(token)
      .then((result) => {
        if (active) setState({ kind: 'done', result });
      })
      .catch((err: unknown) => {
        if (!active) return;
        const message =
          err instanceof ApiError
            ? err.message
            : 'We couldn’t reach the server. Please try again in a moment.';
        setState({ kind: 'error', message });
      });
    return () => {
      active = false;
    };
  }, [token]);

  return (
    <div aria-live="polite">
      {state.kind === 'missing' && (
        <div className="alert alert-danger" role="alert">
          <strong>No confirmation link found</strong>
          <p>
            This page confirms your email using the link we sent you. Please open
            the link directly from your confirmation email.
          </p>
        </div>
      )}

      {state.kind === 'verifying' && (
        <p role="status">Confirming your registration…</p>
      )}

      {state.kind === 'error' && (
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t confirm this link</strong>
          <p>{state.message}</p>
          <p className="follow-up">
            The link may have expired or already been used. You can register again
            from the trainings page.
          </p>
        </div>
      )}

      {state.kind === 'done' && (
        <div
          className={
            state.result.waitlisted ? 'alert alert-warning' : 'alert alert-success'
          }
          role="status"
        >
          <strong>
            {state.result.waitlisted ? 'You’re on the waitlist' : 'You’re confirmed!'}
          </strong>
          <p>{state.result.message}</p>
        </div>
      )}

      <p style={{ marginTop: 'var(--space-6)' }}>
        <Link className="btn btn-secondary" href="/trainings">
          Browse more trainings
        </Link>
      </p>
    </div>
  );
}
