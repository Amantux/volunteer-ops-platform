import { NextRequest, NextResponse } from 'next/server';

// Per-request nonce CSP (Next.js's documented approach). A static `script-src 'self'` would
// block Next's own inline hydration bootstrap scripts and break every client component; a nonce
// lets Next tag its scripts while any script injected through CMS custom-HTML — which cannot know
// the per-request nonce — stays blocked. `'strict-dynamic'` extends that trust to the chunks
// Next's nonced runtime loads. This is the defense-in-depth backstop behind the server-side
// sanitizer (which already strips <script>) and the sandboxed <iframe> used for embeds.
export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64');
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' https: data:",
    "frame-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
  ].join('; ');

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);
  // Next reads the nonce from the CSP on the request headers and applies it to its scripts.
  requestHeaders.set('content-security-policy', csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set('content-security-policy', csp);
  return response;
}

export const config = {
  // Apply to pages, not static assets or the API proxy.
  matcher: [
    {
      source: '/((?!api|_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
};
