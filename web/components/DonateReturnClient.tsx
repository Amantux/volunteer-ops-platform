'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { getDonationStatus, type DonationStatus } from '@/lib/api';
import { formatMinor } from '@/lib/money';

// The return page is refresh-safe: the capability token lives in the URL and the
// server owns the money state, so a reload just re-polls the same donation.
type State =
  | { kind: 'missing' }
  | { kind: 'processing' }
  | { kind: 'succeeded'; status: DonationStatus }
  | { kind: 'failed' };

export default function DonateReturnClient() {
  const params = useSearchParams();
  const token = params.get('token');
  const [state, setState] = useState<State>(
    token ? { kind: 'processing' } : { kind: 'missing' },
  );

  useEffect(() => {
    if (!token) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = () => {
      getDonationStatus(token)
        .then((status) => {
          if (!active) return;
          if (status.status === 'succeeded') {
            setState({ kind: 'succeeded', status });
            return;
          }
          if (status.status === 'failed') {
            setState({ kind: 'failed' });
            return;
          }
          // pending / processing: keep confirming.
          timer = setTimeout(poll, 2000);
        })
        .catch(() => {
          if (!active) return;
          // Transient: the token is durable, so retry rather than error out.
          timer = setTimeout(poll, 2500);
        });
    };
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [token]);

  if (state.kind === 'missing') {
    return (
      <div className="container page donate-narrow">
        <h1>Thank you</h1>
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            💛
          </div>
          <h2>Nothing to confirm here</h2>
          <p>
            This page confirms a gift after checkout. If you were donating, start
            again and we’ll take you through it.
          </p>
          <Link className="btn btn-primary" href="/donate">
            Make a donation
          </Link>
        </div>
      </div>
    );
  }

  if (state.kind === 'processing') {
    return (
      <div className="container page donate-narrow">
        <h1>Confirming your gift</h1>
        <div className="panel processing" role="status" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <h2>Confirming your gift…</h2>
          <p className="muted">
            This only takes a moment. You can keep this tab open.
          </p>
        </div>
      </div>
    );
  }

  if (state.kind === 'failed') {
    return (
      <div className="container page donate-narrow">
        <h1>Your gift didn’t go through</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t complete your payment</strong>
          <p>
            No charge was made. This usually clears up on a second try — you can
            start again below.
          </p>
        </div>
        <Link className="btn btn-primary" href="/donate">
          Try again
        </Link>
      </div>
    );
  }

  const { status } = state;
  return (
    <div className="container page donate-narrow">
      <h1>Thank you for your gift</h1>
      <div className="alert alert-success" role="status">
        <strong>
          Your {formatMinor(status.amount_minor_units, status.currency)} gift is
          confirmed
        </strong>
        <p>
          We’ve emailed your receipt. Your support goes straight to the work our
          community depends on — thank you.
        </p>
      </div>
      <div className="cms-actions">
        <Link className="btn btn-secondary" href="/">
          Back to home
        </Link>
        <Link className="btn btn-secondary" href="/opportunities">
          Find a way to help
        </Link>
      </div>
    </div>
  );
}
