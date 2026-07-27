'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  getHoursReport,
  getMe,
  getToken,
  type HoursReport,
  type Me,
} from '@/lib/auth';

// The permission this surface is gated on (mirrors the backend contract).
const P_VIEW = 'report.view_staffing';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me; report: HoursReport }
  | { kind: 'no-access'; me: Me }
  | { kind: 'error'; message: string };

// Whole where whole, one decimal otherwise; tabular-nums keeps columns aligned.
function formatHours(hours: number): string {
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
}

export default function ReportsClient() {
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
        const report = await getHoursReport();
        setState({ kind: 'ready', me, report });
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
              : 'We couldn’t load the report. Please refresh in a moment.',
        });
      });
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading the report…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Hours &amp; impact</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load the report</strong>
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
            <h1>Hours &amp; impact</h1>
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
            Viewing staffing reports needs the “report.view_staffing”
            permission, which your account doesn’t have. Ask a coordinator to
            grant it.
          </p>
        </div>
      </div>
    );
  }

  const { report } = state;
  const rows = [...report.by_volunteer].sort((a, b) => b.hours - a.hours);

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Hours &amp; impact</h1>
          <p className="muted">
            Approved volunteer hours logged across all events.
          </p>
        </div>
        <Link className="btn btn-secondary" href="/dashboard">
          Back to dashboard
        </Link>
      </div>

      <div className="panel">
        <div className="metric-grid">
          <div className="metric">
            <span className="metric-value">
              {formatHours(report.total_hours)}
            </span>
            <span className="metric-label">Total approved hours</span>
          </div>
          <div className="metric">
            <span className="metric-value">{report.volunteers}</span>
            <span className="metric-label">Volunteers</span>
          </div>
        </div>
      </div>

      <section className="section-gap" aria-labelledby="by-volunteer-heading">
        <h2 id="by-volunteer-heading">Hours by volunteer</h2>
        {rows.length === 0 ? (
          <div className="empty">
            <div className="empty-icon" aria-hidden="true">
              📊
            </div>
            <h3>No hours logged yet</h3>
            <p>
              Approved hours appear here once coordinators log them from the
              roster.
            </p>
          </div>
        ) : (
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col">Volunteer</th>
                <th scope="col" className="num">
                  Hours
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.name}-${i}`}>
                  <td>{r.name}</td>
                  <td className="num">{formatHours(r.hours)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
