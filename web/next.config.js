/** @type {import('next').NextConfig} */
const API_TARGET = process.env.API_REWRITE_TARGET || 'http://localhost:8000';

// The Content-Security-Policy is set per-request (with a nonce) in middleware.ts — a static
// script-src would block Next's inline hydration scripts. These are the static, request-
// independent security headers.
const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
];

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
  async rewrites() {
    // Browser requests to /api/* are proxied server-side to the FastAPI backend.
    // Dev: localhost:8000. Compose: set API_REWRITE_TARGET=http://api:8000.
    return [
      {
        source: '/api/:path*',
        destination: `${API_TARGET}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
