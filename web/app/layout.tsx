import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Riverside Volunteers — Training & Registration',
    template: '%s · Riverside Volunteers',
  },
  description:
    'Riverside Volunteers trains and mobilises neighbours to support our community. Browse trainings and register in minutes.',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <header className="site-header">
          <div className="container">
            <Link className="brand" href="/">
              <span className="brand-mark" aria-hidden="true">
                ♥
              </span>
              Riverside Volunteers
            </Link>
            <nav className="site-nav" aria-label="Primary">
              <Link href="/">Home</Link>
              <Link href="/trainings">Trainings</Link>
            </nav>
          </div>
        </header>

        <main id="main">{children}</main>

        <footer className="site-footer">
          <div className="container">
            <p style={{ margin: 0 }}>
              Riverside Volunteers is a community nonprofit. Questions? Email{' '}
              <a href="mailto:hello@riverside-volunteers.org">
                hello@riverside-volunteers.org
              </a>
              .
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
