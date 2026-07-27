import type { Metadata } from 'next';
import { Suspense } from 'react';
import DonateReturnClient from '@/components/DonateReturnClient';

export const metadata: Metadata = {
  title: 'Thank you',
  description: 'Confirming your donation.',
};

export default function DonateReturnPage() {
  return (
    <Suspense
      fallback={
        <div className="container page donate-narrow">
          <p role="status">Loading…</p>
        </div>
      }
    >
      <DonateReturnClient />
    </Suspense>
  );
}
