import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import RegistrationForm from '@/components/RegistrationForm';
import { formatWhen, getSession, type Session } from '@/lib/api';

export const dynamic = 'force-dynamic';

interface PageProps {
  params: { id: string };
}

function parseId(raw: string): number | null {
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const id = parseId(params.id);
  if (id === null) return { title: 'Training not found' };
  try {
    const session = await getSession(id);
    if (!session) return { title: 'Training not found' };
    return { title: session.course_title, description: session.description };
  } catch {
    return { title: 'Training' };
  }
}

export default async function TrainingDetailPage({ params }: PageProps) {
  const id = parseId(params.id);
  if (id === null) notFound();

  // A true 404 (session not found) renders the not-found page. A connectivity /
  // server failure is different — degrade gracefully instead of a bare 500.
  let session: Session | null;
  try {
    session = await getSession(id);
  } catch {
    return (
      <div className="container page">
        <Link className="back-link" href="/trainings">
          ← Back to all trainings
        </Link>
        <h1>This training couldn&rsquo;t be loaded</h1>
        <div className="alert alert-danger" role="alert">
          <strong>Something went wrong on our end.</strong>
          <p>
            Please try again in a moment. If it keeps happening, email{' '}
            <a href="mailto:contact@gofidog.org">
              contact@gofidog.org
            </a>
            .
          </p>
        </div>
      </div>
    );
  }
  if (!session) notFound();

  return (
    <div className="container page">
      <Link className="back-link" href="/trainings">
        ← Back to all trainings
      </Link>

      <div className="detail-grid">
        <div className="detail">
          <h1>{session.course_title}</h1>
          {session.seats_available ? (
            <p>
              <span className="pill pill-open">Seats available</span>
            </p>
          ) : (
            <p>
              <span className="pill pill-waitlist">Waitlist only</span>
            </p>
          )}

          <p>{session.description}</p>

          <dl>
            <dt>Date &amp; time</dt>
            <dd>{formatWhen(session.starts_at, session.ends_at)}</dd>
            <dt>Location</dt>
            <dd>{session.location || 'To be announced'}</dd>
            <dt>Capacity</dt>
            <dd>
              {session.capacity === null
                ? 'No fixed limit'
                : `${session.capacity} places`}
            </dd>
            <dt>Availability</dt>
            <dd>
              {session.seats_available
                ? 'Places are still open.'
                : 'This session is full — you can join the waitlist below.'}
            </dd>
          </dl>

          <div className="detail-info">
            <section className="detail-info-block">
              <h2>Who can attend</h2>
              <p>Open to everyone — no experience needed.</p>
            </section>
            <section className="detail-info-block">
              <h2>What to bring</h2>
              <p>Just yourself — we provide everything else.</p>
            </section>
            <section className="detail-info-block">
              <h2>Questions?</h2>
              <p>
                Email{' '}
                <a href="mailto:hello@example.org">hello@example.org</a>
              </p>
            </section>
          </div>
        </div>

        <div className="panel">
          <h2>Register for this training</h2>
          <RegistrationForm
            sessionId={session.id}
            full={!session.seats_available}
          />
        </div>
      </div>
    </div>
  );
}
