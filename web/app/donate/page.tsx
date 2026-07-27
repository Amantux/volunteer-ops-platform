import type { Metadata } from 'next';
import { Suspense } from 'react';
import DonateFlowClient from '@/components/DonateFlowClient';

export const metadata: Metadata = {
  title: 'Make a donation',
  description:
    'Support our work with a one-time or monthly gift. Secure checkout — we never see your card details.',
};

export default function DonatePage() {
  return (
    <Suspense
      fallback={
        <div className="container page donate-narrow">
          <p role="status">Loading…</p>
        </div>
      }
    >
      <DonateFlowClient />
    </Suspense>
  );
}
