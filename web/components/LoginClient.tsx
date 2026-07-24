'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { ApiError, login, setToken } from '@/lib/auth';
import RequestLinkForm from '@/components/RequestLinkForm';

type State =
  | { kind: 'verifying' }
  | { kind: 'invalid' } // link bad/expired — offer to request a new one
  | { kind: 'error'; message: string };

export default function LoginClient() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get('token');

  const [state, setState] = useState<State>({ kind: 'verifying' });
  // Guard against React strict-mode double-invocation posting the token twice.
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;
    let active = true;

    login(token)
      .then((res) => {
        setToken(res.token);
        router.replace('/dashboard');
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 409) {
          // Guest account: needs activation before it can sign in.
          router.replace(`/activate?token=${encodeURIComponent(token)}`);
          return;
        }
        if (err instanceof ApiError && err.status === 400) {
          setState({ kind: 'invalid' });
          return;
        }
        setState({
          kind: 'error',
          message:
            err instanceof ApiError
              ? err.message
              : 'We couldn’t reach the server. Please try again in a moment.',
        });
      });

    return () => {
      active = false;
    };
  }, [token, router]);

  // No token in the URL: this is the "request a sign-in link" entry point.
  if (!token) {
    return <RequestLinkForm heading="Sign in" />;
  }

  if (state.kind === 'verifying') {
    return (
      <div aria-live="polite">
        <h1>Signing you in</h1>
        <p role="status">Verifying your sign-in link…</p>
      </div>
    );
  }

  if (state.kind === 'invalid') {
    return (
      <div>
        <div className="alert alert-danger" role="alert">
          <strong>This link is invalid or has expired</strong>
          <p>
            Sign-in links can only be used once and expire after a short time.
            Enter your email below and we’ll send you a fresh one.
          </p>
        </div>
        <RequestLinkForm heading="Request a new link" />
      </div>
    );
  }

  return (
    <div>
      <div className="alert alert-danger" role="alert">
        <strong>We couldn’t sign you in</strong>
        <p>{state.message}</p>
      </div>
      <RequestLinkForm heading="Request a new link" />
    </div>
  );
}
