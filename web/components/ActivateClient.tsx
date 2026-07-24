'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useId, useState } from 'react';
import { activate, ApiError, setToken } from '@/lib/auth';

type Status = 'idle' | 'submitting' | 'error';

export default function ActivateClient() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get('token');

  const passwordId = useId();
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [formError, setFormError] = useState('');

  // No token: the visitor reached this page without an activation link.
  if (!token) {
    return (
      <div>
        <h1>Activate your account</h1>
        <div className="alert alert-danger" role="alert">
          <strong>No activation link found</strong>
          <p>
            This page activates your volunteer account using the link we emailed
            you. Please open that link directly, or{' '}
            <Link href="/login">request a new sign-in link</Link>.
          </p>
        </div>
      </div>
    );
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token) return;
    setFormError('');
    setStatus('submitting');
    try {
      const res = await activate(token, password.trim() || undefined);
      setToken(res.token);
      router.replace('/dashboard');
    } catch (err) {
      setFormError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t reach the server. Please try again in a moment.',
      );
      setStatus('error');
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>Activate your account</h1>
      <p className="lede">
        You’re one step away. Activate your volunteer account to manage your
        shifts. You can set a password now or skip it and keep signing in with
        email links.
      </p>

      <div aria-live="assertive">
        {status === 'error' && formError && (
          <div className="alert alert-danger" role="alert">
            <strong>We couldn’t activate your account</strong>
            <p>{formError}</p>
            <p className="follow-up">
              The link may have expired or already been used. You can{' '}
              <Link href="/login">request a new sign-in link</Link>.
            </p>
          </div>
        )}
      </div>

      <div className="field">
        <label htmlFor={passwordId}>
          Password <span className="muted">(optional)</span>
        </label>
        <p className="hint" id={`${passwordId}-hint`}>
          Optional. Leave blank to keep signing in with email links.
        </p>
        <input
          id={passwordId}
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-describedby={`${passwordId}-hint`}
        />
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-block"
        disabled={status === 'submitting'}
      >
        {status === 'submitting' ? 'Activating…' : 'Activate account'}
      </button>
    </form>
  );
}
