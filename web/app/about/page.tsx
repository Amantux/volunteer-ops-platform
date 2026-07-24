import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'About us',
  description:
    'Riverside Volunteers is a community nonprofit training neighbours to support one another — here is who we are, what volunteers do, and the difference it makes.',
};

export default function AboutPage() {
  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>We&rsquo;re neighbours, not strangers</h1>
          <p className="lede">
            Riverside Volunteers is a community nonprofit built on a simple idea:
            when local people are trained and ready, no one in our neighbourhood
            has to face a hard day alone.
          </p>
          <div className="hero-actions">
            <Link className="btn btn-primary" href="/opportunities">
              Browse opportunities
            </Link>
            <Link className="btn btn-secondary" href="/trainings">
              Browse trainings
            </Link>
          </div>
        </div>
      </section>

      <div className="container page">
        <section aria-labelledby="mission-heading">
          <h2 id="mission-heading">Our mission</h2>
          <p>
            We recruit, train, and organise volunteers from right here in
            Riverside so our community can respond to whatever comes — a storm,
            a food drive, a lonely winter, a neighbour who needs a hand. Every
            training we run is free, because readiness shouldn&rsquo;t depend on
            what you can afford.
          </p>
          <p>
            We believe help works best when it&rsquo;s local, prepared, and
            personal. That&rsquo;s why we invest in people first: teach the
            skills, build the relationships, and trust neighbours to show up for
            one another.
          </p>
        </section>

        <section aria-labelledby="what-heading" className="section-gap">
          <h2 id="what-heading">What volunteers do</h2>
          <p>
            There&rsquo;s no single kind of Riverside volunteer. Some train in
            emergency response and are ready when the sirens sound. Others staff
            our food pantry, drive neighbours to appointments, check in on
            isolated residents, or lend a hand at community events. You choose
            the shifts that fit your life — a few hours a month is plenty.
          </p>
          <p>
            New to all this? Good. Most of our volunteers started with zero
            experience. You take a short, free training, then browse open
            opportunities and sign up for the ones that speak to you.
          </p>
        </section>

        <section aria-labelledby="impact-heading" className="section-gap">
          <h2 id="impact-heading">Our impact</h2>
          <p className="muted">
            What Riverside neighbours accomplished together last year.
          </p>
          <ul
            className="feature-grid"
            style={{ listStyle: 'none', padding: 0 }}
          >
            <li className="feature">
              <h3>600+ neighbours trained</h3>
              <p>
                In first aid, emergency response, and community care — skills
                that stay in the neighbourhood for good.
              </p>
            </li>
            <li className="feature">
              <h3>25,000 volunteer hours</h3>
              <p>
                Given by local people across pantries, wellness checks,
                transport, and events — every hour logged and celebrated.
              </p>
            </li>
            <li className="feature">
              <h3>40 partner organisations</h3>
              <p>
                Schools, shelters, and neighbourhood groups we show up for when
                they need extra hands.
              </p>
            </li>
          </ul>
        </section>

        <section aria-labelledby="story-heading" className="section-gap">
          <h2 id="story-heading">Our story</h2>
          <p>
            Riverside Volunteers started after a flood a decade ago, when a
            handful of neighbours realised the fastest help came not from far
            away but from the people two doors down. They swapped phone numbers,
            learned first aid together, and kept going. That informal phone tree
            grew into the organisation you see today — still run on the same
            belief that the best emergency plan is a prepared community.
          </p>
        </section>

        <section aria-labelledby="join-heading" className="section-gap">
          <h2 id="join-heading">Come be part of it</h2>
          <p className="lede">
            Whether you have a full afternoon or one hour a month, there&rsquo;s a
            place for you here.
          </p>
          <div className="hero-actions" style={{ marginTop: 'var(--space-4)' }}>
            <Link className="btn btn-primary" href="/opportunities">
              Browse opportunities
            </Link>
            <Link className="btn btn-secondary" href="/trainings">
              Browse trainings
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}
