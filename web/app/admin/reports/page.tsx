import type { Metadata } from 'next';
import ReportsClient from '@/components/ReportsClient';

export const metadata: Metadata = {
  title: 'Hours & impact',
  description: 'Approved volunteer hours logged across all events.',
};

export default function ReportsPage() {
  return <ReportsClient />;
}
