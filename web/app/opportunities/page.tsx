import type { Metadata } from 'next';
import Link from 'next/link';
import { formatWhen, getOpportunities, type Opportunity } from '@/lib/api';

function PinIcon() {
  return (
    <svg
      className="pin-icon"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11Z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}

export const metadata: Metadata = {
  title: 'Volunteer opportunities',
  description:
    'Browse open volunteer shifts with Riverside Volunteers and find one that fits your schedule.',
};

// Public content must reflect live availability.
export const dynamic = 'force-dynamic';

function truncate(text: string, max = 160): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max).trimEnd()}…`;
}

// Total open roles across an opportunity's upcoming shifts.
function totalOpenRoles(opp: Opportunity): number {
  return opp.shifts.reduce((sum, s) => sum + s.open_roles, 0);
}

function Availability({ openRoles }: { openRoles: number }) {
  if (openRoles > 0) {
    return (
      <span className="pill pill-open">
        {openRoles} {openRoles === 1 ? 'role open' : 'roles open'}
        <span className="sr-only"> — spots available to sign up</span>
      </span>
    );
  }
  return (
    <span className="pill pill-waitlist">
      Fully staffed
      <span className="sr-only"> — no open roles right now</span>
    </span>
  );
}

export default async function OpportunitiesPage() {
  let opportunities: Opportunity[] | null = null;
  let loadError = false;

  try {
    opportunities = await getOpportunities();
  } catch {
    loadError = true;
  }

  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>Find a way to help</h1>
          <p className="lede">
            These are the shifts our neighbours need covered right now. Pick one
            that fits your week — sign in to claim your spot, and we&rsquo;ll take
            it from there.
          </p>
          <div className="hero-actions">
            <Link className="btn btn-primary" href="/login">
              Sign in to sign up
            </Link>
            <Link className="btn btn-secondary" href="/trainings">
              Browse trainings
            </Link>
          </div>
        </div>
      </section>

      <div className="container page">
        {loadError && (
          <div className="alert alert-danger" role="alert">
            <strong>We couldn&rsquo;t load opportunities right now.</strong>
            <p>
              Please refresh the page in a moment. If it keeps happening, email{' '}
              <a href="mailto:hello@riverside-volunteers.org">
                hello@riverside-volunteers.org
              </a>
              .
            </p>
          </div>
        )}

        {!loadError && opportunities && opportunities.length === 0 && (
          <div className="empty">
            <div className="empty-icon" aria-hidden="true">
              🌱
            </div>
            <h2>Nothing open just now</h2>
            <p>No open opportunities right now — check back soon.</p>
            <Link className="btn btn-primary" href="/trainings">
              Browse trainings
            </Link>
          </div>
        )}

        {!loadError && opportunities && opportunities.length > 0 && (
          <>
            <p className="result-count">
              {opportunities.length} open{' '}
              {opportunities.length === 1 ? 'opportunity' : 'opportunities'}
            </p>
            <ul className="card-list">
              {opportunities.map((opp) => {
                const openRoles = totalOpenRoles(opp);
                return (
                  <li className="card" key={opp.event_id}>
                    <div className="card-link">
                      <h2>{opp.title}</h2>
                      <p className="card-when">
                        Next shift: {formatWhen(opp.next_shift_at, null)}
                      </p>
                      <p className="desc">{truncate(opp.description)}</p>
                      <div className="card-meta">
                        <span className="card-location">
                          <PinIcon />
                          {opp.location || 'Location to be announced'}
                        </span>
                        {opp.kind && (
                          <span className="muted card-kind">{opp.kind}</span>
                        )}
                        <span className="card-shift-count muted">
                          {opp.shift_count}{' '}
                          {opp.shift_count === 1 ? 'shift' : 'shifts'}
                        </span>
                        <Availability openRoles={openRoles} />
                      </div>
                      <Link className="card-cta" href="/login">
                        Sign in to sign up →
                      </Link>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </>
  );
}
