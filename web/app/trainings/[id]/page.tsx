import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import RegistrationForm from '@/components/RegistrationForm';
import { getSession } from '@/lib/api';

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

  const session = await getSession(id);
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
