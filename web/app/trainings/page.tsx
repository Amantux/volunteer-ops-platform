import type { Metadata } from 'next';
import Link from 'next/link';
import { getSessions, type Session } from '@/lib/api';

export const metadata: Metadata = {
  title: 'Trainings',
  description: 'Browse and register for upcoming volunteer training sessions.',
};

// Public content must reflect live availability.
export const dynamic = 'force-dynamic';

function truncate(text: string, max = 140): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max).trimEnd()}…`;
}

function Availability({ session }: { session: Session }) {
  if (session.seats_available) {
    return (
      <span className="pill pill-open">
        Seats available
        <span className="sr-only"> for this session</span>
      </span>
    );
  }
  return (
    <span className="pill pill-waitlist">
      Waitlist only
      <span className="sr-only"> — session is full</span>
    </span>
  );
}

export default async function TrainingsPage() {
  let sessions: Session[] | null = null;
  let loadError = false;

  try {
    sessions = await getSessions();
  } catch {
    loadError = true;
  }

  return (
    <div className="container page">
      <h1>Upcoming trainings</h1>
      <p className="lede">
        Free sessions run by Riverside Volunteers. Pick one to see details and
        register.
      </p>

      {loadError && (
        <div className="alert alert-danger" role="alert">
          <strong>We couldn&rsquo;t load trainings right now.</strong>
          <p>
            Please refresh the page in a moment. If it keeps happening, email{' '}
            <a href="mailto:hello@riverside-volunteers.org">
              hello@riverside-volunteers.org
            </a>
            .
          </p>
        </div>
      )}

      {!loadError && sessions && sessions.length === 0 && (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            📅
          </div>
          <h2>No trainings scheduled yet</h2>
          <p>
            We&rsquo;re planning our next sessions. Check back soon, or email us to
            be notified when new trainings open.
          </p>
          <a
            className="btn btn-primary"
            href="mailto:hello@riverside-volunteers.org"
          >
            Notify me
          </a>
        </div>
      )}

      {!loadError && sessions && sessions.length > 0 && (
        <ul className="card-list">
          {sessions.map((s) => (
            <li className="card" key={s.id}>
              <Link className="card-link" href={`/trainings/${s.id}`}>
                <h2>{s.course_title}</h2>
                <p className="desc">{truncate(s.description)}</p>
                <div className="card-meta">
                  <span>📍 {s.location || 'Location to be announced'}</span>
                  <Availability session={s} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
