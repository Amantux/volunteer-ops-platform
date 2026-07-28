import type { Metadata } from 'next';
import Link from 'next/link';
import { formatWhen, getSessions, type Session } from '@/lib/api';

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
        Free sessions run by Golden Opportunities for Independence. Pick one to see details and
        register.
      </p>

      {loadError && (
        <div className="alert alert-danger" role="alert">
          <strong>We couldn&rsquo;t load trainings right now.</strong>
          <p>
            Please refresh the page in a moment. If it keeps happening, email{' '}
            <a href="mailto:contact@gofidog.org">
              contact@gofidog.org
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
          <h2>No trainings scheduled right now</h2>
          <p>
            No trainings scheduled right now — email us to hear when new sessions
            open.
          </p>
          <a
            className="btn btn-primary"
            href="mailto:contact@gofidog.org"
          >
            Email us
          </a>
        </div>
      )}

      {!loadError && sessions && sessions.length > 0 && (
        <>
          <p className="result-count">
            {sessions.length} upcoming{' '}
            {sessions.length === 1 ? 'training' : 'trainings'}
          </p>
          <ul className="card-list">
            {sessions.map((s) => (
              <li className="card" key={s.id}>
                <Link className="card-link" href={`/trainings/${s.id}`}>
                  <h2>{s.course_title}</h2>
                  <p className="card-when">
                    {formatWhen(s.starts_at, s.ends_at)}
                  </p>
                  <p className="desc">{truncate(s.description)}</p>
                  <div className="card-meta">
                    <span className="card-location">
                      <PinIcon />
                      {s.location || 'Location to be announced'}
                    </span>
                    <Availability session={s} />
                  </div>
                  <span className="card-cta" aria-hidden="true">
                    View details →
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
