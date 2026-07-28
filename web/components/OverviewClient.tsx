'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  getMe,
  getOverview,
  getToken,
  type Me,
  type OverviewData,
} from '@/lib/auth';
import { formatMinor } from '@/lib/money';

// The permission this surface is gated on (mirrors the backend contract).
const P_VIEW = 'report.view_staffing';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me; overview: OverviewData }
  | { kind: 'no-access'; me: Me }
  | { kind: 'error'; message: string };

// Whole where whole, one decimal otherwise; tabular-nums keeps columns aligned.
function formatHours(hours: number): string {
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
}

// Application states arrive as machine keys (e.g. "under_review"); present them
// as readable labels without inventing meaning.
function humanizeState(state: string): string {
  return state
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function OverviewClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });

  const load = useCallback(() => {
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
        const overview = await getOverview();
        setState({ kind: 'ready', me, overview });
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace('/login');
          return;
        }
        setState({
          kind: 'error',
          message:
            err instanceof ApiError
              ? err.message
              : 'We couldn’t load the overview. Please refresh in a moment.',
        });
      });
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading the overview…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Executive overview</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load the overview</strong>
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
            <h1>Executive overview</h1>
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
            Viewing the executive overview needs the “report.view_staffing”
            permission, which your account doesn’t have. Ask an administrator to
            grant it.
          </p>
        </div>
      </div>
    );
  }

  const { overview } = state;
  const funnel = Object.entries(overview.applications_by_state).sort(
    (a, b) => b[1] - a[1],
  );
  const donations = overview.donations;
  // A representative currency for the donation KPI cards (single-currency per
  // org in practice); the overview payload carries no currency, so use USD.
  const cur = 'USD';

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Executive overview</h1>
          <p className="muted">
            Org-wide snapshot of volunteers, shifts, applications, and giving.
          </p>
        </div>
        <div className="cms-actions">
          <Link className="btn btn-secondary" href="/admin/reports">
            View reports
          </Link>
          <Link className="btn btn-secondary" href="/dashboard">
            Back to dashboard
          </Link>
        </div>
      </div>

      <section aria-labelledby="staffing-heading">
        <h2 id="staffing-heading" className="sr-only">
          Staffing at a glance
        </h2>
        <div className="panel">
          <div className="metric-grid">
            <Kpi
              label="Active volunteers"
              value={String(overview.active_volunteers)}
            />
            <Kpi
              label="Upcoming shifts (next 7 days)"
              value={String(overview.upcoming_shifts_7d)}
            />
            <Kpi
              label="Approved hours"
              value={formatHours(overview.approved_hours)}
            />
          </div>
        </div>
      </section>

      <section className="section-gap" aria-labelledby="funnel-heading">
        <h2 id="funnel-heading">Application funnel</h2>
        {funnel.length === 0 ? (
          <div className="empty">
            <div className="empty-icon" aria-hidden="true">
              🗂️
            </div>
            <h3>No applications yet</h3>
            <p>
              Applications appear here by state as soon as prospective volunteers
              start applying.
            </p>
          </div>
        ) : (
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col">State</th>
                <th scope="col" className="num">
                  Applications
                </th>
              </tr>
            </thead>
            <tbody>
              {funnel.map(([name, count]) => (
                <tr key={name}>
                  <td>{humanizeState(name)}</td>
                  <td className="num">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {donations && (
        <section className="section-gap" aria-labelledby="donations-heading">
          <h2 id="donations-heading">Donations</h2>
          <div className="panel">
            <div className="metric-grid">
              <Kpi
                label="Total raised"
                value={formatMinor(donations.volume_minor_units, cur)}
              />
              <Kpi label="Donors" value={String(donations.donor_count)} />
              <Kpi
                label="Monthly recurring"
                value={formatMinor(donations.recurring_mrr_minor_units, cur)}
              />
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span className="metric-value">{value}</span>
      <span className="metric-label">{label}</span>
    </div>
  );
}
