import Link from 'next/link';

export default function HomePage() {
  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>Where every volunteer, recipient &amp; dog becomes family.</h1>
          <p className="lede">
            Golden Opportunities for Independence breeds and trains Golden Retriever service,
            facility, and crisis-response dogs. Our volunteer puppy raisers are the backbone of
            the program — and there&rsquo;s a place for you in it.
          </p>
          <div className="hero-actions">
            <Link className="btn btn-primary" href="/opportunities">
              Get involved
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
              <h3>1. Find a way to help</h3>
              <p>
                Browse volunteer opportunities and upcoming info sessions — from
                puppy raising to events. No experience required.
              </p>
            </li>
            <li className="feature">
              <h3>2. Sign up in minutes</h3>
              <p>
                Add your name and email. If something&rsquo;s full, we&rsquo;ll place
                you on the waitlist automatically.
              </p>
            </li>
            <li className="feature">
              <h3>3. Join the GOFI family</h3>
              <p>
                Check your inbox and confirm. We&rsquo;ll be in touch about next
                steps — and you&rsquo;ll be part of raising a life-changing dog.
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
            Explore current volunteer opportunities and info sessions, and sign up
            for the ones that speak to you.
          </p>
          <Link className="btn btn-secondary" href="/opportunities">
            Get involved
          </Link>
        </section>
      </div>
    </>
  );
}
