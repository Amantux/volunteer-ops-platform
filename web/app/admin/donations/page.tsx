import type { Metadata } from 'next';
import DonationsClient from '@/components/DonationsClient';

export const metadata: Metadata = {
  title: 'Donations',
  description: 'Donation totals, recent gifts, and finance exports.',
};

export default function DonationsPage() {
  return <DonationsClient />;
}
