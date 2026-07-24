import type { Metadata } from 'next';
import { Suspense } from 'react';
import LoginClient from '@/components/LoginClient';

export const metadata: Metadata = {
  title: 'Sign in',
  description: 'Sign in to manage your volunteer shifts.',
};

export default function LoginPage() {
  return (
    <div className="container page auth-narrow">
      <Suspense fallback={<p role="status">Loading…</p>}>
        <LoginClient />
      </Suspense>
    </div>
  );
}
