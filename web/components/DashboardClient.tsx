'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ApiError, clearToken, getMe, getToken, type Me } from '@/lib/auth';
import VolunteerPanel from '@/components/VolunteerPanel';
import CoordinatorPanel from '@/components/CoordinatorPanel';

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; me: Me }
  | { kind: 'error'; message: string };

function isVolunteer(me: Me): boolean {
  return (
    me.has_volunteer_profile ||
    me.permissions.includes('shift.signup') ||
    me.permissions.includes('shift.view_eligible')
  );
}

function isCoordinator(me: Me): boolean {
  return (
    me.permissions.includes('shift.view_roster') ||
    me.permissions.includes('report.view_staffing')
  );
}

export default function DashboardClient() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: 'loading' });

  useEffect(() => {
    // No token at all: don't even ask the server.
    if (!getToken()) {
      router.replace('/login');
      return;
    }

    let active = true;
    getMe()
      .then((me) => {
        if (active) setState({ kind: 'ready', me });
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          // authFetch already cleared the token.
          router.replace('/login');
          return;
        }
        setState({
          kind: 'error',
          message:
            err instanceof ApiError
              ? err.message
              : 'We couldn’t load your dashboard. Please refresh in a moment.',
        });
      });

    return () => {
      active = false;
    };
  }, [router]);

  function signOut() {
    clearToken();
    router.replace('/');
  }

  if (state.kind === 'loading') {
    return (
      <div className="container page">
        <p role="status">Loading your dashboard…</p>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="container page">
        <h1>Dashboard</h1>
        <div className="alert alert-danger" role="alert">
          <strong>We couldn’t load your dashboard</strong>
          <p>{state.message}</p>
        </div>
      </div>
    );
  }

  const { me } = state;
  const volunteer = isVolunteer(me);
  const coordinator = isCoordinator(me);

  return (
    <div className="container page">
      <div className="page-head">
        <div>
          <h1>Welcome back, {me.name}</h1>
          <p className="muted">{me.email}</p>
        </div>
        <div className="cms-actions">
          <Link className="btn btn-secondary" href="/admin/overview">
            Overview
          </Link>
          <Link className="btn btn-secondary" href="/admin/schedule">
            Schedule
          </Link>
          <Link className="btn btn-secondary" href="/admin/site">
            Manage site
          </Link>
          <Link className="btn btn-secondary" href="/admin/social">
            Social
          </Link>
          <Link className="btn btn-secondary" href="/admin/requests">
            Requests
          </Link>
          <Link className="btn btn-secondary" href="/admin/enrollments">
            Enrollments
          </Link>
          <Link className="btn btn-secondary" href="/admin/campaigns">
            Campaigns
          </Link>
          <Link className="btn btn-secondary" href="/admin/donations">
            Donations
          </Link>
          <Link className="btn btn-secondary" href="/admin/reports">
            Reports
          </Link>
          <Link className="btn btn-secondary" href="/admin/assistant">
            AI Assistant
          </Link>
          <button type="button" className="btn btn-secondary" onClick={signOut}>
            Sign out
          </button>
        </div>
      </div>

      {!volunteer && !coordinator && (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            👋
          </div>
          <h2>You’re signed in</h2>
          <p>
            Your account doesn’t have any shifts or rosters assigned yet. A
            coordinator will be in touch — check back soon.
          </p>
        </div>
      )}

      {volunteer && (
        <div className="dashboard-section">
          <VolunteerPanel />
        </div>
      )}

      {coordinator && (
        <div className="dashboard-section">
          <CoordinatorPanel />
        </div>
      )}
    </div>
  );
}
