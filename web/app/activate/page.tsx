import type { Metadata } from 'next';
import { Suspense } from 'react';
import ActivateClient from '@/components/ActivateClient';

export const metadata: Metadata = {
  title: 'Activate your account',
  description: 'Activate your volunteer account to manage your shifts.',
};

export default function ActivatePage() {
  return (
    <div className="container page auth-narrow">
      <Suspense fallback={<p role="status">Loading…</p>}>
        <ActivateClient />
      </Suspense>
    </div>
  );
}
