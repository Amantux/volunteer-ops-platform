'use client';

import { useId, useState } from 'react';
import { ApiError, registerForSession, type RegisterResult } from '@/lib/api';

interface Props {
  sessionId: number;
  full: boolean;
}

interface FieldErrors {
  name?: string;
  email?: string;
}

type Status = 'idle' | 'submitting' | 'success' | 'error';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function RegistrationForm({ sessionId, full }: Props) {
  const baseId = useId();
  const nameId = `${baseId}-name`;
  const emailId = `${baseId}-email`;
  const phoneId = `${baseId}-phone`;

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState('');
  const [result, setResult] = useState<RegisterResult | null>(null);

  function validate(): boolean {
    const next: FieldErrors = {};
    if (!name.trim()) next.name = 'Please enter your name.';
    if (!email.trim()) {
      next.email = 'Please enter your email.';
    } else if (!EMAIL_RE.test(email.trim())) {
      next.email = 'Please enter a valid email address.';
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError('');
    if (!validate()) return;

    setStatus('submitting');
    try {
      const res = await registerForSession(sessionId, {
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
      });
      setResult(res);
      setStatus('success');
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
      } else {
        setFormError('We couldn’t reach the server. Please check your connection and try again.');
      }
      setStatus('error');
    }
  }

  // Success view replaces the form (registration is complete).
  if (status === 'success' && result) {
    return (
      <div aria-live="polite">
        <div
          className={result.waitlisted ? 'alert alert-warning' : 'alert alert-success'}
          role="status"
        >
          <strong>
            {result.waitlisted ? 'You’re on the waitlist' : 'You’re almost registered!'}
          </strong>
          <p>{result.message}</p>
        </div>
        <p className="follow-up">
          📧 Please check your email and click the confirmation link to secure your
          place. It can take a minute to arrive — remember to check your spam folder.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      {full && (
        <div className="alert alert-warning" role="note">
          <strong>This session is currently full.</strong>
          <p>You can still register below to join the waitlist.</p>
        </div>
      )}

      {/* Live region for form-level errors */}
      <div aria-live="assertive">
        {status === 'error' && formError && (
          <div className="alert alert-danger" role="alert">
            <strong>We couldn’t complete your registration</strong>
            <p>{formError}</p>
          </div>
        )}
      </div>

      <div className="field">
        <label htmlFor={nameId}>
          Full name <span className="req" aria-hidden="true">*</span>
        </label>
        <input
          id={nameId}
          name="name"
          type="text"
          autoComplete="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-required="true"
          aria-invalid={errors.name ? 'true' : undefined}
          aria-describedby={errors.name ? `${nameId}-error` : undefined}
        />
        {errors.name && (
          <p className="field-error" id={`${nameId}-error`}>
            {errors.name}
          </p>
        )}
      </div>

      <div className="field">
        <label htmlFor={emailId}>
          Email address <span className="req" aria-hidden="true">*</span>
        </label>
        <p className="hint" id={`${emailId}-hint`}>
          We’ll send a confirmation link here.
        </p>
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
          aria-invalid={errors.email ? 'true' : undefined}
          aria-describedby={
            errors.email ? `${emailId}-hint ${emailId}-error` : `${emailId}-hint`
          }
        />
        {errors.email && (
          <p className="field-error" id={`${emailId}-error`}>
            {errors.email}
          </p>
        )}
      </div>

      <div className="field">
        <label htmlFor={phoneId}>
          Phone <span className="muted">(optional)</span>
        </label>
        <input
          id={phoneId}
          name="phone"
          type="tel"
          autoComplete="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-block"
        disabled={status === 'submitting'}
      >
        {status === 'submitting'
          ? 'Submitting…'
          : full
            ? 'Join the waitlist'
            : 'Register'}
      </button>

      <p className="form-trust">
        No account needed. We&rsquo;ll only email you about this session and
        won&rsquo;t share your details.
      </p>
    </form>
  );
}
