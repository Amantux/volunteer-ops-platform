/** @type {import('next').NextConfig} */
const API_TARGET = process.env.API_REWRITE_TARGET || 'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
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
