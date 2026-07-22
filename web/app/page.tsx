import Link from 'next/link';

export default function HomePage() {
  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>Neighbours helping neighbours, ready when it counts.</h1>
          <p className="lede">
            Riverside Volunteers trains local people to support our community —
            from emergency response to everyday care. Every session is free, and
            every skill makes a difference.
          </p>
          <div className="hero-actions">
            <Link className="btn btn-primary" href="/trainings">
              Browse trainings
            </Link>
            <a className="btn btn-secondary" href="#how-it-works">
              How it works
            </a>
          </div>
        </div>
      </section>

      <div className="container page">
        <section aria-labelledby="how-it-works">
          <h2 id="how-it-works">How it works</h2>
          <ul className="feature-grid" style={{ listStyle: 'none', padding: 0 }}>
            <li className="feature">
              <h3>1. Find a training</h3>
              <p>
                Browse upcoming sessions and pick one that fits your schedule and
                interests. No experience required.
              </p>
            </li>
            <li className="feature">
              <h3>2. Register in minutes</h3>
              <p>
                Add your name and email. If a session is full, we&rsquo;ll place
                you on the waitlist automatically.
              </p>
            </li>
            <li className="feature">
              <h3>3. Confirm your spot</h3>
              <p>
                Check your inbox and click the confirmation link. That&rsquo;s it —
                we&rsquo;ll see you there.
              </p>
            </li>
          </ul>
        </section>

        <section
          aria-labelledby="cta-heading"
          style={{ marginTop: 'var(--space-8)' }}
        >
          <h2 id="cta-heading">Ready to get started?</h2>
          <p className="lede">
            Explore our current trainings and register for the ones that speak to
            you.
          </p>
          <Link className="btn btn-primary" href="/trainings">
            See upcoming trainings
          </Link>
        </section>
      </div>
    </>
  );
}
