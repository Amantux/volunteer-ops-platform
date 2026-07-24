import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Contact',
  description:
    'Get in touch with Riverside Volunteers — email us, find our community hub, and see our hours.',
};

// NOTE: There is no contact-form backend, so we deliberately do not render a
// form that would post nowhere. A clear mailto CTA is the honest choice. A
// hosted contact form is a future CMS / forms-engine item.

export default function ContactPage() {
  return (
    <div className="container page">
      <h1>Get in touch</h1>
      <p className="lede">
        Questions about volunteering, training, or partnering with us?
        We&rsquo;d love to hear from you — a real person reads every message.
      </p>

      <div className="detail-grid">
        <section aria-labelledby="email-heading" className="panel">
          <h2 id="email-heading">Email us</h2>
          <p>
            The fastest way to reach us. Tell us a little about how you&rsquo;d
            like to help or what you need, and we&rsquo;ll reply within two
            working days.
          </p>
          <p>
            <a
              className="btn btn-primary"
              href="mailto:hello@riverside-volunteers.org"
            >
              Email hello@riverside-volunteers.org
            </a>
          </p>
          <p className="muted" style={{ marginBottom: 0 }}>
            Prefer to browse first? See our{' '}
            <Link href="/faq">frequently asked questions</Link>.
          </p>
        </section>

        <section aria-labelledby="visit-heading" className="panel">
          <h2 id="visit-heading">Find us</h2>
          <div className="detail">
            <dl>
              <dt>Community hub</dt>
              <dd>
                Riverside Volunteers
                <br />
                14 Millbank Street
                <br />
                Riverside
              </dd>
              <dt>Hours</dt>
              <dd>
                Monday to Friday, 9:00&ndash;17:00
                <br />
                Saturday, 10:00&ndash;14:00
                <br />
                Closed Sundays and public holidays
              </dd>
              <dt>Email</dt>
              <dd>
                <a href="mailto:hello@riverside-volunteers.org">
                  hello@riverside-volunteers.org
                </a>
              </dd>
            </dl>
          </div>
        </section>
      </div>

      <section
        aria-labelledby="contact-cta"
        className="section-gap"
        style={{ maxWidth: '720px' }}
      >
        <h2 id="contact-cta">Rather just dive in?</h2>
        <p className="lede">
          You don&rsquo;t need to email first — browse what&rsquo;s open and sign
          up whenever you&rsquo;re ready.
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
  );
}
