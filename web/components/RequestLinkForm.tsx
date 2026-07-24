'use client';

import { useId, useState } from 'react';
import { ApiError, requestLogin } from '@/lib/auth';

type Status = 'idle' | 'submitting' | 'sent' | 'error';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Requests a one-time sign-in link. The backend responds identically whether or
// not the address is registered, so we always show the same neutral message.
export default function RequestLinkForm({
  heading = 'Sign in',
}: {
  heading?: string;
}) {
  const emailId = useId();
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [fieldError, setFieldError] = useState('');
  const [formError, setFormError] = useState('');
  const [message, setMessage] = useState('');

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFieldError('');
    setFormError('');

    const value = email.trim();
    if (!value) {
      setFieldError('Please enter your email.');
      return;
    }
    if (!EMAIL_RE.test(value)) {
      setFieldError('Please enter a valid email address.');
      return;
    }

    setStatus('submitting');
    try {
      const res = await requestLogin(value);
      setMessage(
        res.message ||
          'If that email is registered, a sign-in link is on its way.',
      );
      setStatus('sent');
    } catch (err) {
      setFormError(
        err instanceof ApiError
          ? err.message
          : 'We couldn’t reach the server. Please check your connection and try again.',
      );
      setStatus('error');
    }
  }

  if (status === 'sent') {
    return (
      <div aria-live="polite">
        <div className="alert alert-success" role="status">
          <strong>Check your email</strong>
          <p>{message}</p>
        </div>
        <p className="follow-up">
          The link can take a minute to arrive — remember to check your spam
          folder. It expires shortly for your security.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>{heading}</h1>
      <p className="lede">
        Enter your email and we’ll send you a secure sign-in link. No password
        needed.
      </p>

      <div aria-live="assertive">
        {status === 'error' && formError && (
          <div className="alert alert-danger" role="alert">
            <strong>We couldn’t send your sign-in link</strong>
            <p>{formError}</p>
          </div>
        )}
      </div>

      <div className="field">
        <label htmlFor={emailId}>Email address</label>
        <input
          id={emailId}
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-required="true"
          aria-invalid={fieldError ? 'true' : undefined}
          aria-describedby={fieldError ? `${emailId}-error` : undefined}
        />
        {fieldError && (
          <p className="field-error" id={`${emailId}-error`}>
            {fieldError}
          </p>
        )}
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-block"
        disabled={status === 'submitting'}
      >
        {status === 'submitting' ? 'Sending…' : 'Send sign-in link'}
      </button>
    </form>
  );
}
