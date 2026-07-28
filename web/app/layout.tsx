import type { Metadata } from 'next';
import Link from 'next/link';
import AuthNav from '@/components/AuthNav';
import ChatAssistant from '@/components/ChatAssistant';
import { getSiteNav, type SiteNavItem } from '@/lib/api';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Golden Opportunities for Independence — Training & Registration',
    template: '%s · Golden Opportunities for Independence',
  },
  description:
    'Golden Opportunities for Independence (GOFI) breeds and trains Golden Retriever service, facility, and crisis-response dogs. Volunteer, foster a puppy, or support our mission.',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Published CMS pages that opted into the menu. Resilient: if the site-nav
  // fetch fails, fall back to just the built-in links.
  let cmsNav: SiteNavItem[] = [];
  try {
    cmsNav = await getSiteNav();
  } catch {
    cmsNav = [];
  }

  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to main content
        </a>
        <header className="site-header">
          <div className="container">
            <Link className="brand" href="/" title="Golden Opportunities for Independence">
              <span className="brand-mark" aria-hidden="true">
                🐾
              </span>
              GOFI
            </Link>
            <nav className="site-nav" aria-label="Primary">
              <Link href="/">Home</Link>
              <Link href="/opportunities">Opportunities</Link>
              <Link href="/trainings">Trainings</Link>
              <Link href="/calendar">Calendar</Link>
              {/* About and other built-in pages are now CMS-managed and appear via cmsNav. */}
              {cmsNav.map((item) => (
                <Link key={item.slug} href={`/${item.slug}`}>
                  {item.title}
                </Link>
              ))}
              <AuthNav />
            </nav>
          </div>
        </header>

        <main id="main">{children}</main>

        <footer className="site-footer">
          <div className="container">
            <nav className="footer-nav" aria-label="Footer">
              <Link href="/faq">FAQ</Link>
              <Link href="/contact">Contact</Link>
            </nav>
            <p style={{ margin: 0 }}>
              Golden Opportunities for Independence is a 501(c)(3) nonprofit in Walpole, MA.
              Questions? Email{' '}
              <a href="mailto:contact@gofidog.org">
                contact@gofidog.org
              </a>
              .
            </p>
          </div>
        </footer>

        {/* Floating assistant — self-hides when there is no session token. */}
        <ChatAssistant />
      </body>
    </html>
  );
}
