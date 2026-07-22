import type { Metadata } from 'next';
import { Suspense } from 'react';
import VerifyClient from '@/components/VerifyClient';

export const metadata: Metadata = {
  title: 'Confirm your email',
};

export default function VerifyPage() {
  return (
    <div className="container page">
      <h1>Confirm your registration</h1>
      <Suspense fallback={<p role="status">Loading…</p>}>
        <VerifyClient />
      </Suspense>
    </div>
  );
}
