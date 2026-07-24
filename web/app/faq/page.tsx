import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'FAQ',
  description:
    'Answers to common questions about volunteering with Riverside Volunteers — signing up, training, time commitment, age, accessibility, and tracking hours.',
};

interface QA {
  q: string;
  a: React.ReactNode;
}

// Answers reflect how the platform actually works: magic-link sign-in,
// training-then-opportunities, and automatic waitlists.
const FAQS: QA[] = [
  {
    q: 'How do I sign up to volunteer?',
    a: (
      <>
        <p>
          Start by browsing our{' '}
          <Link href="/opportunities">opportunities</Link> or{' '}
          <Link href="/trainings">trainings</Link>. When you&rsquo;re ready,
          enter your email and we&rsquo;ll send you a secure sign-in link — no
          password to remember. Click the link and you&rsquo;re in.
        </p>
        <p>
          From your dashboard you can register for trainings and claim open
          shifts in a couple of taps.
        </p>
      </>
    ),
  },
  {
    q: 'Do I need any experience?',
    a: (
      <p>
        None at all. Most Riverside volunteers started with no background in
        this work. Our free trainings teach you everything you need, and there
        are always experienced volunteers alongside you on a shift.
      </p>
    ),
  },
  {
    q: 'How much time does it take?',
    a: (
      <p>
        It&rsquo;s entirely up to you. Some people give a few hours a month;
        others do more. You only sign up for the specific shifts that fit your
        schedule — there&rsquo;s no ongoing obligation and no minimum you have to
        hit.
      </p>
    ),
  },
  {
    q: 'Do I have to complete training first?',
    a: (
      <p>
        For most roles, yes — a short, free training comes first so you feel
        confident and everyone stays safe. Once you&rsquo;ve completed the
        relevant training, the matching opportunities open up on your dashboard
        under &ldquo;Shifts you can join.&rdquo;
      </p>
    ),
  },
  {
    q: 'What happens if a training or shift is full?',
    a: (
      <p>
        You can still sign up — we&rsquo;ll add you to the waitlist
        automatically and let you know by email the moment a place opens. Spots
        free up more often than you&rsquo;d think, so it&rsquo;s always worth
        joining.
      </p>
    ),
  },
  {
    q: 'Is there a minimum age to volunteer?',
    a: (
      <p>
        Volunteers must be at least 16. Some roles that involve driving or
        certain emergency response tasks require you to be 18 — the requirement
        is noted on each opportunity. Younger neighbours are welcome at many of
        our community events when accompanied by a guardian.
      </p>
    ),
  },
  {
    q: 'What should I bring to a shift?',
    a: (
      <p>
        Just yourself, comfortable clothes and shoes, and a water bottle. If a
        particular role needs anything specific — sturdy footwear, a warm layer,
        proof of a completed training — it&rsquo;ll be listed on the shift
        details before you arrive.
      </p>
    ),
  },
  {
    q: 'Can you accommodate accessibility needs?',
    a: (
      <p>
        Yes. We want everyone who wants to help to be able to. Many roles can be
        adapted, and we offer seated, remote, and low-mobility options. Email{' '}
        <a href="mailto:hello@riverside-volunteers.org">
          hello@riverside-volunteers.org
        </a>{' '}
        and tell us what you need — we&rsquo;ll find a fit together.
      </p>
    ),
  },
  {
    q: 'How are my volunteer hours tracked?',
    a: (
      <p>
        Your shift coordinator logs your hours after each shift, and they add up
        automatically on your dashboard. If you ever need a record for school,
        work, or an award, just email us and we&rsquo;ll send a confirmation.
      </p>
    ),
  },
  {
    q: 'How do I cancel if I can&rsquo;t make it?',
    a: (
      <p>
        Life happens. Sign in, open the shift on your dashboard, and cancel — the
        sooner the better, so we can offer your place to someone on the
        waitlist. There&rsquo;s no penalty for cancelling.
      </p>
    ),
  },
];

export default function FaqPage() {
  return (
    <div className="container page">
      <h1>Frequently asked questions</h1>
      <p className="lede">
        Everything a first-time volunteer usually wants to know. Still stuck?{' '}
        <Link href="/contact">Get in touch</Link> and we&rsquo;ll help.
      </p>

      <div className="faq-list">
        {FAQS.map((item) => (
          <details className="faq-item" key={item.q}>
            <summary>{item.q}</summary>
            <div className="faq-answer">{item.a}</div>
          </details>
        ))}
      </div>

      <section
        aria-labelledby="faq-cta"
        className="section-gap"
        style={{ maxWidth: '720px' }}
      >
        <h2 id="faq-cta">Ready to start?</h2>
        <p className="lede">
          Browse what&rsquo;s open and sign up for your first training or shift.
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
